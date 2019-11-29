#! /usr/bin/env python3

import argparse
import sys
import re
import asyncio
import importlib
import traceback

import utils.yaml

import measurement.hot_connect
import measurement.agentinterface
import agent.to_collector

VERBOSE = False
quit_signal = False

class AgentTable():
    def __init__(self, fields, mode=None):
        self.fields = fields

        table_names = {field.partition(".")[0] for field in fields if field != "time"}
        if len(table_names) != 1:
            raise Exception(f"Not unique table name: {table_names} in {fields}")

        self.table_name = (mode+"." if mode else "") + table_names.pop()

        if VERBOSE:
            print(self.table_name, "|", ", ".join(fields))

        if self.table_name == "quality":
            self.rows = []

    def add(self, *row):
        if not AgentExperiment.new_table_row:
            if AgentExperiment.new_table_row is None:
                print("Warning: nothing to do with the table rows ...")
                AgentExperiment.new_table_row = False
            return

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

def prepare_cfg(key):
    cfg = {}

    cfg_filename = "smart_agent.yaml"
    smart_cfg = utils.yaml.load_multiple(cfg_filename)
    if key is None: key = smart_cfg["default"]
    if not key in smart_cfg:
        raise KeyError(f"Key '{key}' not found inside {cfg_filename}")

    # gather the measurment sets requested for this run
    cfg["measurements"] = list()
    for measures in smart_cfg[key].get("measurement_sets", []):
        for measure in smart_cfg["measurement_sets"][measures]:
            if isinstance(measure, str) and measure in cfg["measurements"]:
                continue
            cfg["measurements"].append(measure)

    cfg["run_as_collector"] = smart_cfg[key].get("run_as_collector", False)
    cfg["run_headless"] = smart_cfg[key].get("run_headless", False)
    cfg["run_as_viewer"] = smart_cfg[key].get("run_as_viewer", False)
    if cfg["run_as_viewer"] and cfg["run_headless"]:
        print(f"ERROR: viewer cannot run headless (key: '{key}')")
        raise RuntimeError()

    try:
        cfg["port_to_collector"] = smart_cfg[key]["port_to_collector"]
    except KeyError: pass # ignore here, not used for collector/viewer

    machines_key = smart_cfg["setup"]["machines"]
    cfg["machines"] = smart_cfg["machines"][machines_key]
    cfg["ui.web"] = smart_cfg["setup"]["ui.web"]

    if cfg["run_headless"]:
        cfg["ui.web"]["headless"] = smart_cfg[key]["headless"]['ui.web']

    return cfg

def load_measurements(cfg, expe):
    measurements = []
    name_re = re.compile(r'^[a-z_][a-z0-9_]*$', re.I)
    for measurement_name in cfg['measurements']:
        if isinstance(measurement_name, dict):
            measurement_name, measurement_options = list(measurement_name.items())[0]
        else:
            measurement_options = {}

        if not name_re.match(measurement_name):
            raise Exception(f'Invalid module name: {measurement_name}')

        measurement_options['machines'] = cfg['machines']

        measurement_module = importlib.import_module('measurement.' + measurement_name.lower())
        measurement_class = getattr(measurement_module, measurement_name)
        measurements.append(measurement_class(measurement_options, expe))

        if not hasattr(measurements[-1], "live"):
            raise Exception(f"Module {measurement_name} cannot run live ...")
    return measurements

def checkup_mods(measurements, deads, loop):
    for mod in measurements:
        while mod.live and mod.live.exception:
            ex, info = mod.live.exception.pop()
            print(mod, "raised", ex.__class__.__name__, ex)
            if VERBOSE:
                traceback.print_exception(*info)

        # try to reconnect disconnected agent interfaces

        if not (mod.live and mod.live.alive):
            if not mod in deads:
                print(mod, "is dead")
                deads.append(mod)

            try:
                mod.start()
                mod.live.connect(loop, mod.process_line)
            except Exception as e:
                print("###", e.__class__.__name__+":", e)
                if VERBOSE:
                    fatal = sys.exc_info()
                    traceback.print_exception(*fatal)
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
        import ui.web
        ui.web.AgentExperimentClass = AgentExperiment
        server = ui.web.Server(expe, headless=run_headless)
        server.configure(cfg['ui.web'], cfg['machines'])

    else: # run as agent
        port = cfg["port_to_collector"]
        print(f"\n* Starting the socket for the Perf Collector on {port}...")
        server = agent.to_collector.Server(port, expe, loop)

    AgentExperiment.new_table = server.new_table
    AgentExperiment.new_table_row = server.new_table_row

    deads = []
    measurements = load_measurements(cfg, expe) if not run_as_viewer else []

    measurement.hot_connect.setup(measurements, deads)

    print("\n* Preparing the environment ...")
    for mod in measurements:
        mod.setup()
        deads.append(mod)

    server.start()
    print("\n* Running!")
    RECHECK_TIME=5 #s

    async def timer_kick(wait_time):
        for _ in range(wait_time):
            # this allows asyncio to check for loop.stop every 1s
            await asyncio.sleep(1)

        loop.stop()
        loop.create_task(timer_kick(RECHECK_TIME))

    fatal = None
    loop.create_task(timer_kick(RECHECK_TIME))

    while not quit_signal:
        try:
            server.periodic_checkup()
            checkup_mods(measurements, deads, loop)

        except Exception as e:
            print(f"FATAL: {e.__class__.__name__} raised during periodic checkup: {e}")
            fatal = sys.exc_info()
            break

        loop.run_forever() # returns after timer_kick() calls loop.stop()

    print("\n* Stopping the measurements ...")
    for m in measurements:
        try:
            m.stop()
        except Exception as e:
            if fatal:
                continue
            print(f"ERROR: {e.__class__.__name__} raised "
                  f"while stopping {m.__class__.__name__}: {e}")

    server.terminate()

    return fatal



async def shutdown(signal, loop):
    print("\nQuitting ...")

    global quit_signal
    quit_signal = True

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks: task.cancel()

    # Cancelling outstanding tasks
    await asyncio.gather(*tasks, return_exceptions=True)

    loop.stop()

def prepare_gracefull_shutdown():
    import signal
    loop = asyncio.get_event_loop()

    for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown(s, loop)))

def main():
    prepare_gracefull_shutdown()

    key = None if len(sys.argv) == 1 else sys.argv[1]

    try:
        cfg = prepare_cfg(key)
    except Exception as e:
        print(f"Fatal: {e.__class__.__name__}: {e}")
        return 1

    error = run(cfg)
    if error:
        traceback.print_exception(*error)
        return 1

    return 0

def get_wsgi_application():
    import ui.web
    ui.web.AgentExperimentClass = AgentExperiment
    server = ui.web.Server(expe=None)

    AgentExperiment.new_table = server.new_table
    AgentExperiment.new_table_row = server.new_table_row

    return ui.web.main_app.server

if __name__ == "__main__":
    sys.exit(main())
