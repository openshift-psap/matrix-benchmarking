import socket
import struct
import asyncio
import collections
import struct

import measurement
import measurement.perf_collect
import utils.live

#---

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1230
DEFAULT_MODE = "local"

class Quality():
    def __init__(self, expe, fields):
        self.fields = fields
        self.expe = expe

    def add(self, values):
        ts = int(values[0])
        src = values[1][1:-1]
        msg = values[2][1:-1].replace("||", ",")

        self.expe.new_quality(ts, src, msg)

def create_table(experiment, line, mode=None):
    # line: "#3 frames|client.mm_time;client.frame_size;client.time;client.decode_duration;client.queue"
    table_uname, fields_name = line.split("|")
    table_name = table_uname.split(" ")[1]

    fields = fields_name.split(";")
    if table_name == "quality":
        table = Quality(experiment, fields)
    else:
        table = experiment.create_table(fields, mode)

    return table_uname, table


async def async_read_dataset(reader):
    b_line = b""
    while True:
        b_char = await reader.read(1)
        if b_char == b"\0": break
        if not b_char: return False
        b_line += b_char

    return b_line


class Perf_Collect(measurement.Measurement):
    def __init__(self, cfg, experiment):
        measurement.Measurement.__init__(self, experiment)
        self.experiment = experiment

        self.tables = None
        self.live = None
        self.current_table = None
        self.current_table_uname = None

        self.host = cfg.get("host", DEFAULT_HOST)
        self.port = cfg.get("port", DEFAULT_PORT)
        self.mode = cfg.get("mode", DEFAULT_MODE)

    def initialize_localagent(self):
        nb_tables = struct.unpack("I", self.sock.recv(4))[0]

        print(f"Received {nb_tables} table definitions")
        tables = {}
        for _ in range(nb_tables):
            msg = ""
            last = b""
            while last != b"\0":
                last = self.sock.recv(1)
                msg += last.decode("ascii")

            table_uname, table = create_table(self.experiment, msg[:-1], self.mode)

            tables[table_uname] = table

        return tables

    def send_quality(self, quality_msg):
        print(">>>", quality_msg)
        self.sock.send((quality_msg + "\0").encode("ascii"))

    def setup(self):
        self.experiment.send_quality_cbs.append(self.send_quality)

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((self.host, self.port))
        except ConnectionRefusedError:
            raise Exception("Cannot connect to the SmartLocalAgent on "
                            f"{self.host}:{self.port} ({self.mode})")

        self.tables = self.initialize_localagent()

        self.live = utils.live.LiveSocket(self.sock, async_read_dataset)

    def stop(self):
        self.live = None

    def process_line(self, buf):
        line = buf.decode("ascii")
        if line.startswith("#"): # eg: '#3 frames'
            self.current_table_uname, lenght = line.split("|")
            self.current_table = self.tables[self.current_table_uname]
        else:
            line_tuple = line[1:-1].split(", ")

            def cast(elt):
                if elt == "None": import pdb;pdb.set_trace()
                return float(elt) if ("." in elt or "e" in elt) else int(elt)

            if isinstance(self.current_table, Quality):
                self.current_table.add(line_tuple)
            else:
                entry = [cast(elt) for elt in line_tuple]
                self.current_table.add(*entry)
