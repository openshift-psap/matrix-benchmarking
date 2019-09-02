#! /usr/bin/env python3

import argparse
import sys
import threading
import re
import asyncio
import importlib
import signal
import socket
import select
import traceback
import struct

import utils.yaml
from experiment import Experiment
from measurement import ProcessNotRunningMeasurementException

quit_signal = False
def signal_handler(sig, frame):
    global quit_signal
    if quit_signal: return
    print("\nQuitting ...")
    quit_signal = True
    loop = asyncio.get_event_loop()
    loop.stop()

signal.signal(signal.SIGINT, signal_handler)

import measurement.agentinterface

quality_buffer = []
def sock_read_quality(sock):
    try:
        c = sock.recv(1).decode("ascii")
        if c == "\0":
            measurement.agentinterface.quality.send_str("".join(quality_buffer))
            quality_buffer[:] = []
        else:
            quality_buffer.append(c)

        return True
    except Exception:
        return False

def accept_socket(server_socket):
    read_list = [server_socket]
    running = True
    while running:

        readable, writable, errored = select.select(read_list, [], [])

        for s in readable:
            if s == server_socket:
                try:
                    conn, addr = server_socket.accept()

                except OSError as e:
                    if e.errno == 22: #  Invalid argument
                        running = False
                        break

                print("New connection from", addr)
                new_clients.append(conn)
                read_list.append(conn)
            else:
                if not sock_read_quality(s):
                    read_list.remove(conn)

    print("Perf collector socket closed.")

new_clients = []
current_clients = []
old_quality_message = []

def initialize_server():
    serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serv.setblocking(0)
    serv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        PORT = 1230
        serv.bind(('0.0.0.0', PORT))
    except OSError as e:
        if e.errno == 98:
            print(f"Port {PORT} already in use. Is the SmartLocalAgent already running?")
            return None, None
        else:
            raise e

    serv.listen(5)
    thr = threading.Thread(target=accept_socket, args=[serv])
    thr.start()

    return thr, serv


def initialize_new_client(client_sock, expe):
    client_sock.send(struct.pack("I", len(expe.tables)))
    for i, table in enumerate(expe.tables):
        msg = f"#{i} {table.table_name}|" +";".join([f for f in table.fields]) + "\0"
        client_sock.send(msg.encode("ascii"))


def send_quality_backlog(client_sock, expe):
    table = expe.quality
    if not (table and table.rows):
        return

    client_sock.send(f"#{table.tid} {table.table_name}|{len(table.rows)}\0".encode("ascii"))
    for row in table.rows:
        client_sock.send(str(row).encode("ascii") + b"\0")

def initialize_new_clients(expe):
    global new_clients
    clients, new_clients = new_clients, [] # should be atomic

    for client in clients:
        initialize_new_client(client, expe)
        send_quality_backlog(client, expe)
        current_clients.append(client)


def send_all(line):
    for client in current_clients[:]:
        try:
            client.send(line + b"\0")
        except Exception as e:
            # safe as we're using a copy of the list
            current_clients.remove(client)
            print(f"Client {client.getsockname()} disconnected ({e})")

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

    def add(self, *args):
        send_all(f"#{self.tid} {self.table_name}|1".encode("ascii"))
        send_all(str(args).encode("ascii"))

        if self.table_name == "quality":
            self.rows.append(args)

class AgentExperiment():
    def __init__(self, cfg):
        self.tables = []
        self.quality = None
        self.tid = 0

    def create_table(self, fields):
        table = AgentTable(self.tid, self, fields)
        self.tid += 1

        if table.table_name == "quality":
            assert self.quality is None, "Quality table already created ..."
            self.quality = table

        self.tables.append(table)
        return table

    def truncate(self):
        pass


def run(cfg):
    global quit_signal

    # load and initialize measurements
    experiment = AgentExperiment(cfg)

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
        measurements.append(measurement_class(measurement_options, experiment))

        if not hasattr(measurements[-1], "live"):
            raise Exception(f"Module {measurement_name} cannot run live ...")

    print("\n* Preparing the environment ...")
    for m in measurements: m.setup()

    print("\n* Starting the Perf Collector socket ...")

    serv_thr, serv_sock = initialize_server()
    if serv_sock is None:
        return

    loop = asyncio.get_event_loop()

    async def timer_kick(wait_time):
        await asyncio.sleep(wait_time)
        loop.stop()

    print("\n* Running!")

    fatal = None
    while True:
        RECHECK_TIME=5 #s
        loop.create_task(timer_kick(RECHECK_TIME))

        try:
            for mod in measurements:
                # try to reconnect disconnected agent interfaces
                if not (mod.live and mod.live.alive):
                    print(mod, "is dead")
                    try:
                        mod.start()
                        mod.live.connect(loop, mod.process_line)
                    except Exception as e:
                        print("###", e.__class__.__name__, e)

        except Exception as e:
            print(f"FATAL: {e.__class__.__name__} raised while processing: {e}")
            fatal = sys.exc_info()
            break

        # returns after timer_kick() calls loop.stop()
        loop.run_forever()

        try:
            initialize_new_clients(experiment)
        except Exception as e:
            print(f"FATAL: {e.__class__.__name__} raised while sending: {e}")
            fatal = sys.exc_info()
            quit_signal = True

        if quit_signal: break

    print("\n* Preparing the environment ...")
    for m in measurements: m.stop()

    serv_sock.shutdown(socket.SHUT_RDWR)
    if fatal:
        traceback.print_exception(*fatal)

    return 0

def main():
    # some arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--dry-run', action='store_true', help='dry live run')

    args = parser.parse_args()

    smart_cfg = utils.yaml.load_multiple("smart_agent.yaml")

    cfg = {}

    key = "default" #if len(sys.argv) == 1 else sys.argv[1]
    if not key in smart_cfg:
        print(f"ERROR: invalid parameter: {key}")

    # gather the measurment sets requested for this run
    cfg["measurements"] = list()
    for measures in smart_cfg[key]["measurement_sets"]:
        for measure in smart_cfg["measurement_sets"][measures]:
            if isinstance(measure, str) and measure in cfg["measurements"]:
                continue
            cfg["measurements"].append(measure)

    cfg["machines"] = smart_cfg["machines"]

    #localmachine = dict(type="local")
    #cfg["machines"] = dict(guest=localmachine, host=localmachine, client=localmachine)

    sys.exit(run(cfg))

if __name__ == "__main__":
    main()
