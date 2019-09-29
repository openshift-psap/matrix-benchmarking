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
        self.tables = {}

    def create_table(self, line):
        self.__class__.do_create_table(self.experiment, line, self.mode, self.tables)

    @staticmethod
    def do_create_table(experiment, line, mode, tables=None):
        # line: "frames|client.mm_time;client.frame_size;client.time;client.decode_duration;client.queue"

        table_name, fields_name = line.split("|")
        fields = fields_name.split(";")

        if tables and table_name in tables:
            old_fields = tables[table_name].fields

            if (len(old_fields) != len(fields) or
                any([a != b for a, b in zip(old_fields, fields)])
            ):
                print(f"ERROR: Trying to re-create table {table_name} with different fields")
                print(f"ERROR: Old fields: {', '.join(old_fields)}")
                print(f"ERROR: New fields: {', '.join(fields)}")
                raise AttributeError()
            else:
                print(f"INFO: Table '{table_name}' is already known.")
                return

        if table_name == "quality":
            table = Quality(experiment, fields)
        else:
            table = experiment.create_table(fields, mode)

        if tables is not None:
            tables[table_name] = table

        return table

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

            if not msg.startswith("#"): import pdb;pdb.set_trace()

            # eg: msg = '#client-pid|time;client-pid.cpu_user;client-pid.cpu_system\0'
            self.create_table(msg[1:-1])

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

        self.initialize_localagent()

        self.live = utils.live.LiveSocket(self.sock, async_read_dataset)

    def stop(self):
        self.live = None

    def process_line(self, buf):
        line = buf.decode("ascii")

        if line.startswith("#"): # eg: '#client-pid|time;client-pid.cpu_user;client-pid.cpu_system' --> new table
            self.create_table(line[1:])

        elif line.startswith("@"): # eg: '@frames' --> new 'frames' records comming next
            self.current_table_uname, lenght = line[1:].split("|")
            try:
                self.current_table = self.tables[self.current_table_uname]
            except KeyError as e:
                import pdb;pdb.set_trace()
                pass
        else:
            line_tuple = line[1:-1].split(", ")

            def cast(elt):
                try:
                    return float(elt) if ("." in elt or "e" in elt) else int(elt)
                except ValueError:
                    import pdb;pdb.set_trace()
                    pass
            if isinstance(self.current_table, Quality):
                self.current_table.add(line_tuple)
            else:
                entry = [cast(elt) for elt in line_tuple]
                self.current_table.add(*entry)
