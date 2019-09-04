import socket
import struct
import asyncio
import collections
import struct

import measurement
import measurement.perf_collect
import utils.live

#---

HOST = "localhost"
PORT = 1230

class Quality():
    def __init__(self, expe, fields):
        self.fields = fields
        self.expe = expe

    def add(self, values):
        ts = int(values[0])
        src = values[1][1:-1]
        msg = values[2][1:-1].replace("||", ",")

        self.expe.new_quality(ts, src, msg)

def initialize(sock, experiment):
    nb_tables = struct.unpack("I", sock.recv(4))[0]

    print(f"Receive {nb_tables} table definitions")
    tables = {}
    for _ in range(nb_tables):
        msg = ""
        last = b""
        while last != b"\0":
            last = sock.recv(1)
            msg += last.decode("ascii")

        # eg:
        "#3 frames|client.mm_time;client.frame_size;client.time;client.decode_duration;client.queue\0"
        table_uname, fields_name = msg[:-1].split("|")
        table_name = table_uname.split(" ")[1]

        fields = fields_name.split(";")
        if table_name == "quality":
            tables[table_uname] = Quality(experiment, fields)
            continue

        tables[table_uname] = experiment.create_table(fields)
    return tables


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
        self.live = True
        self.current_table = None
        self.current_table_uname = None

    def send_quality(self, quality_msg):
        print(">>>", quality_msg)
        self.sock.send((quality_msg + "\0").encode("ascii"))

    def setup(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((HOST, PORT))
        except ConnectionRefusedError:
            raise Exception(f"Cannot cannot to the SmartLocalAgent on {HOST}:{PORT}")

        self.tables = initialize(self.sock, self.experiment)

        self.live = utils.live.LiveSocket(self.sock, async_read_dataset)

        self.experiment.send_quality_cb = self.send_quality

    def start(self):
        pass

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
