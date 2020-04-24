#! /usr/bin/env python3.7

import argparse
import sys, signal
import re
import asyncio
import importlib
import traceback
import datetime, calendar

import utils.yaml

import measurement.hot_connect
import measurement.agentinterface
import agent.to_collector

DEBUG = False

if DEBUG:
    import warnings; warnings.simplefilter('always', ResourceWarning)
    import tracemalloc; tracemalloc.start()

quit_signal = False

class AgentTable():
    def __init__(self, fields, mode=None):
        self.fields = fields

        table_names = {field.partition(".")[0] for field in fields if field != "time"}
        if len(table_names) != 1:
            raise Exception(f"Not unique table name: {table_names} in {fields}")

        self.table_name = (mode+"." if mode else "") + table_names.pop()

        if DEBUG:
            print(self.table_name, "|", ", ".join(fields))

        if self.table_name == "quality":
            self.rows = []

    def add(self, *row, **kw_row):
        if not AgentExperiment.new_table_row:
            if AgentExperiment.new_table_row is None:
                print("Warning: nothing to do with the table rows ...")
                AgentExperiment.new_table_row = False
            return

        if kw_row:
            row = list(row)
            for table_field in self.fields[len(row):]:
                fieldname = table_field.partition(".")[-1]
                row.append(kw_row[fieldname])

        AgentExperiment.new_table_row(self, row)

        if self.table_name == "quality":
            self.rows.append(row)

    def header(self):
        return f"#{self.table_name}|{';'.join(self.fields)}"

class AgentExperiment():
    new_table = None
    new_table_row = None

    def __init__(self):
        self.tables = {}
        self.quality = None
        self.new_quality_cb = None
        self.send_quality_cbs = []
        self.agent_status = {}

    def create_table(self, fields, mode=None):
        table = AgentTable(fields, mode)

        try:
            return self.tables[table.table_name]
        except KeyError: pass # new table, proceed

        if table.table_name == "quality":
            assert self.quality is None, "Quality table already created ..."
            self.quality = table

        if AgentExperiment.new_table:
            AgentExperiment.new_table(table)

        self.tables[table.table_name] = table

        return table

    def send_quality(self, msg):
        if not self.send_quality_cbs:
            print("No callback set for sending quality message: ", msg)
            return

        print("Quality to send:", msg)
        for send_quality_cb in self.send_quality_cbs:
            send_quality_cb(msg)

    def set_quality_callback(self, cb):
        self.new_quality_callback = cb

    def new_quality(self, ts, src, msg):
        if self.new_quality_cb:
            self.new_quality_cb(ts, src, msg)

    def agents_connected(self):
        return [k for k, v in self.agent_status.items() if v.live and v.live.alive]

def prepare_cfg(mode_key, agent_key):
    cfg = {"mode": mode_key, "agent": agent_key}

    cfg_filename = f"cfg/{mode_key}/agents.yaml"

    agents_cfg = utils.yaml.load_multiple(cfg_filename)
    if not agent_key in agents_cfg:
        raise KeyError(f"Key '{agent_key}' not found inside '{cfg_filename}'")

    # gather the measurment sets requested for this run
    cfg["measurements"] = list()
    for measures in agents_cfg[agent_key].get("measurement_sets", []):
        for measure in agents_cfg["measurement_sets"][measures]:
            if isinstance(measure, str) and measure in cfg["measurements"]: continue
            cfg["measurements"].append(measure)

    cfg["run_as_collector"] = agents_cfg[agent_key].get("run_as_collector", False)
    cfg["run_headless"] = agents_cfg[agent_key].get("run_headless", False)
    cfg["run_as_viewer"] = agents_cfg[agent_key].get("run_as_viewer", False)

    if cfg["run_as_viewer"] and cfg["run_headless"]:
        print(f"ERROR: viewer cannot run headless (key: '{agent_key}')")
        raise RuntimeError()

    if cfg["run_as_viewer"]:
        cfg["matrix_view"] = agents_cfg[agent_key].get("matrix_view")

    try: cfg["port_to_collector"] = agents_cfg[agent_key]["port_to_collector"]
    except KeyError: pass # ignore here, not used for collector/viewer

    if cfg["run_headless"]: cfg["headless"] = agents_cfg[agent_key]["headless"]

    machines_key = agents_cfg["setup"]["machines"]
    cfg["machines"] = agents_cfg["machines"][machines_key]

    cfg["plugin"] = agents_cfg["plugins"].get(mode_key, {})

    cfg["setup"] = agents_cfg["setup"]

    return cfg

def load_measurements(cfg, expe):
    measurements = []

    for name in cfg['measurements']:
        if isinstance(name, dict):
            name, options = list(name.items())[0]
        else:
            options = {}

        options['machines'] = cfg['machines']

        for mod_prefix in f"plugins.{cfg['mode']}.", "":
            try: mod = importlib.import_module(f"{mod_prefix}measurement.{name.lower()}")
            except ModuleNotFoundError: continue
            break
        else: raise RuntimeError("Cannot find measurement module '{name}' ...")

        clazz = getattr(mod, name)
        measurements.append(clazz(options, expe))

        if not hasattr(measurements[-1], "live"):
            raise Exception(f"Module {measurement_name} cannot run live ...")

    return measurements

def checkup_mods(measurements, deads, loop):
    for mod in measurements:
        while mod.live and mod.live.exception:
            ex, info = mod.live.exception.pop()
            print(mod, "raised", ex.__class__.__name__, ex)
            if DEBUG:
                traceback.print_exception(*info)

        # try to reconnect disconnected agent interfaces

        if not (mod.live and mod.live.alive):
            if not mod in deads:
                print(mod, "is dead")
                deads.append(mod)
                mod.stop()
            try:
                mod.start()
                if mod.live:
                    mod.live.connect(loop, mod.process_line)
            except Exception as e:
                #print("###", e.__class__.__name__+":", e)
                if DEBUG:
                    fatal = sys.exc_info()
                    traceback.print_exception(*fatal)
            else:
                if mod.live and mod.live.alive:
                    # module restarted without error
                    try: deads.remove(mod)
                    except ValueError: pass
        else:
            try: deads.remove(mod)
            except ValueError: pass

def run(cfg):
    run_as_collector = cfg["run_as_collector"]
    run_headless = cfg["run_headless"]
    run_as_viewer = cfg["run_as_viewer"]

    loop = asyncio.get_event_loop()

    expe = AgentExperiment() if not run_as_viewer else None

    if run_as_collector or run_as_viewer:
        import ui # load ui only in collector/viewer modes
        ui.AgentExperimentClass = AgentExperiment
        server = ui.Server(expe, headless=run_headless, cfg=cfg)

    else: # run as agent
        port = cfg["port_to_collector"]
        print(f"\n* Starting the socket for the Perf Collector on {port}...")
        agent.to_collector.force_recheck = force_recheck
        import utils.live
        utils.live.force_recheck = force_recheck
        server = agent.to_collector.Server(port, expe, loop)

    AgentExperiment.new_table = server.new_table
    AgentExperiment.new_table_row = server.new_table_row

    deads = []
    measurements = load_measurements(cfg, expe) if not run_as_viewer else []

    measurement.hot_connect.setup(measurements, deads, force_recheck)

    print("\n* Preparing the environment ...")
    for mod in measurements:
        mod.setup()
        deads.append(mod)

    server.start()
    print("\n* Running!")

    fatal = []

    loop.create_task(check_timer(server, measurements, deads, loop, fatal))
    while not quit_signal:
        loop.run_forever()

    print("\n* Stopping the measurements ...")

    for m in measurements:
        try:
            m.stop() # measurements
        except Exception as e:
            if fatal: continue
            print(f"ERROR: {e.__class__.__name__} raised "
                  f"while stopping {m.__class__.__name__}: {e}")

    server.terminate()

    return fatal

async def shutdown(signal, loop):
    print("\nQuitting ...")

    global quit_signal
    quit_signal = True

    tasks = [t for t in list(asyncio.all_tasks()) if t is not asyncio.current_task()]
    for task in tasks: task.cancel()

    # Cancelling outstanding tasks
    await asyncio.gather(*tasks, return_exceptions=True)

    loop.stop()

def prepare_gracefull_shutdown():
    loop = asyncio.get_event_loop()

    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR2):
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown(s, loop)))

RECHECK_TIME=5 #s
force_recheck = []
async def check_timer(server, measurements, deads, loop, fatal):
    while True:
        try:
            server.periodic_checkup()
            checkup_mods(measurements, deads, loop)
        except Exception as e:
            print(f"FATAL: {e.__class__.__name__} raised during periodic checkup: {e}")
            fatal.append(sys.exc_info())
            global quit_signal
            quit_signal = True

        force_recheck[:] = []
        for _ in range(RECHECK_TIME):
            # this allows asyncio to check for loop.stop every 1s
            await asyncio.sleep(1)
            if force_recheck: break

def main():
    MODE_KEY = "adaptive"
    prepare_gracefull_shutdown()

    try:
        agent_key = sys.argv[1]
    except IndexError:
        print(f"FATAL: Please provide an <agent_key> as first parameter.")
        return 1

    try:
        cfg = prepare_cfg(MODE_KEY, agent_key)
    except KeyError as e:
        print(f"ERROR: {e.args[0]}")
        error = None
    except Exception as e:
        print(f"FATAL: {e.__class__.__name__}: {e}")
        error = sys.exc_info()
    else:
        error = run(cfg)

    if error:
        traceback.print_exception(*error)
        return 1

    return 0

def get_wsgi_application():
    import ui
    ui.AgentExperimentClass = AgentExperiment
    server = ui.Server(expe=None, cfg=None)

    AgentExperiment.new_table = server.new_table
    AgentExperiment.new_table_row = server.new_table_row

    return ui.main_app.server

if __name__ == "__main__":
    sys.exit(main())
