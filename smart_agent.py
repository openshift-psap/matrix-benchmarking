#! /usr/bin/env python3

import argparse
import sys
import re
import asyncio
import importlib
import signal
import traceback

import utils.yaml

import measurement.agentinterface
import agent.to_collector


quit_signal = False
def signal_handler(sig, frame):
    global quit_signal
    if quit_signal: return
    print("\nQuitting ...")
    quit_signal = True
    loop = asyncio.get_event_loop()
    loop.stop()


class AgentTable():
    def __init__(self, tid, expe, fields):
        self.fields = fields
        self.expe = expe
        self.tid = tid

        table_names = {field.partition(".")[0] for field in fields if field != "time"}
        if len(table_names) != 1:
            raise Exception(f"Not unique table name: {table_names} in {fields}")
        self.table_name = table_names.pop()

        if self.table_name == "quality":
            self.rows = []

    def add(self, *row):
        if self.expe.new_table_row is None:
            print("Warning: nothing to do with the table rows ...")
            self.expe.new_table_row = False
            return

        self.expe.new_table_row(self, row)

        if self.table_name == "quality":
            self.rows.append(row)


class AgentExperiment():
    def __init__(self):
        self.tables = []
        self.quality = None
        self.tid = 0
        self.new_table = None
        self.new_table_row = None
        self.new_quality_cb = None


    def create_table(self, fields):
        table = AgentTable(self.tid, self, fields)
        self.tid += 1

        if table.table_name == "quality":
            assert self.quality is None, "Quality table already created ..."
            self.quality = table

        if self.new_table:
            self.new_table(table)

        self.tables.append(table)
        return table

    def send_quality(self, msg):
        if not self.send_quality_cb:
            print("No callback set for sending quality message: ", msg)
            return
        self.send_quality_cb(msg)

    def set_quality_callback(self, cb):
        self.new_quality_callback = cb

    def new_quality(self, ts, src, msg):
        if self.new_quality_cb:
            self.new_quality_cb(ts, src, msg)

def prepare_cfg(key):
    cfg = {}

    cfg_filename = "smart_agent.yaml"
    smart_cfg = utils.yaml.load_multiple(cfg_filename)

    if not key in smart_cfg:
        raise KeyError(f"Key '{key}' not found inside {cfg_filename}")

    # gather the measurment sets requested for this run
    cfg["measurements"] = list()
    for measures in smart_cfg[key]["measurement_sets"]:
        for measure in smart_cfg["measurement_sets"][measures]:
            if isinstance(measure, str) and measure in cfg["measurements"]:
                continue
            cfg["measurements"].append(measure)

    cfg["machines"] = smart_cfg["machines"]

    cfg["run_as_agent"] = smart_cfg[key]["run_as_agent"]
    #localmachine = dict(type="local")
    #cfg["machines"] = dict(guest=localmachine, host=localmachine, client=localmachine)

    return cfg


def load_measurements(cfg, expe):
    measurements = []
    name_re = re.compile(r'^[a-z_][a-z0-9_]*$', re.I)
    for measurement_name in cfg['measurements']:
        measurement_options = None

        if isinstance(measurement_name, dict):
            measurement_name, measurement_options = list(measurement_name.items())[0]

        if not name_re.match(measurement_name):
            raise Exception(f'Invalid module name: {measurement_name}')

        measurement_module = importlib.import_module('measurement.' + measurement_name.lower())
        measurement_class = getattr(measurement_module, measurement_name)
        measurements.append(measurement_class(measurement_options, expe))

        if not hasattr(measurements[-1], "live"):
            raise Exception(f"Module {measurement_name} cannot run live ...")
    return measurements

def checkup_mods(measurements, deads, loop):
    for mod in measurements:
        # try to reconnect disconnected agent interfaces
        if not (mod.live and mod.live.alive):
            if not mod in deads:
                print(mod, "is dead")
                deads.append(mod)

            try:
                mod.start()
                mod.live.connect(loop, mod.process_line)
            except Exception as e:
                print("###", e.__class__.__name__, e)
        else:
            try: deads.remove(mod)
            except ValueError: pass
def run(cfg):
    run_as_agent = cfg["run_as_agent"]
    expe = AgentExperiment()

    loop = asyncio.get_event_loop()

    if run_as_agent:
        print("\n* Starting the socket for the Perf Collector...")
        server = agent.to_collector.Server(expe, loop)
    else: # run as collector
        import ui.web
        server = ui.web.Server()

    expe.new_table = server.new_table
    expe.new_table_row = server.new_table_row

    # load and initialize measurements
    measurements = load_measurements(cfg, expe)

    deads = []
    print("\n* Preparing the environment ...")
    for mod in measurements:
        mod.setup()
        deads.append(mod)

    async def timer_kick(wait_time):
        await asyncio.sleep(wait_time)
        loop.stop()

    print("\n* Running!")

    fatal = None
    RECHECK_TIME=5 #s
    while not quit_signal:
        try:
            server.periodic_checkup()
            checkup_mods(measurements, deads, loop)

        except Exception as e:
            print(f"FATAL: {e.__class__.__name__} raised during periodic checkup: {e}")
            fatal = sys.exc_info()
            break

        loop.create_task(timer_kick(RECHECK_TIME))
        loop.run_forever() # returns after timer_kick() calls loop.stop()

    print("\n* Stoping the measurements ...")
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


def main():
    signal.signal(signal.SIGINT, signal_handler)

    key = "central_agent" if len(sys.argv) == 1 else sys.argv[1]

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

if __name__ == "__main__":
    sys.exit(main())
