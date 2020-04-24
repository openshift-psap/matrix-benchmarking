import socket, struct, asyncio
import collections

import measurement
import utils.live
from measurement.quality import quality
#---

def sock_readline(sock):
    string = ""
    while True:
        c = sock.recv(1).decode("ascii")

        if not c: return False
        if c == '\n': return string

        string += c

async def async_readline(reader):
   while True:
       data = await reader.readline()
       if reader.at_eof(): return False

       return data.decode("ascii")[:-1] # return without the trailing '\n'


Entry = collections.namedtuple("RecorderEntry", "name function loc time msg")
async def async_read_entry(reader):
    # example of message:
    """
Name: stream_channel_data
Where: stream_channel_send_item
Time: 529462
stream-channel.c:315:Stream data packet size 212621 mm_time 313704699
""" # + empty line

    name = await async_readline(reader)
    where = await async_readline(reader)
    time = await async_readline(reader)
    loc_msg = await async_readline(reader)
    empty = await async_readline(reader)

    if False in (name, where, time, loc_msg, empty):
        return False

    loc_file, loc_line, msg = loc_msg.split(":", 2)

    if empty:
        print(f"WARNING: entry separator not empty: '{empty}'")

    return Entry(name.partition(": ")[-1],
                 where.partition(": ")[-1],
                 f"{loc_file}:{loc_line}",
                 int(time.partition(": ")[-1]),
                 msg)

#---

def initialize(sock, mode):
    recorders = sock_readline(sock)
    if recorders is False:
        return False

    # eg: "Recorders: stream_channel_data;stream_device_data;"
    names = recorders[:-1].partition(": ")[-1].split(";")

    # enable all the recorders
    for name in names:
        sock.sendall(struct.pack("c", '1'.encode("ascii")))

    print(f"{mode}: received {len(names)} recorders: {', '.join(names)}")

    return names

#---

class AgentInterface(measurement.Measurement):
    def __init__(self, cfg, experiment):
        measurement.Measurement.__init__(self, experiment)

        self.processors = {}

        self.live = None

        self.host = cfg.get("host", "localhost")
        self.port = cfg["port"]
        self.mode = cfg["mode"]

    def __str__(self):
        return f"AgentInterface:{self.mode}<{self.host}:{self.port}>"

    def setup(self):
        raise NotImplementedError("Should be overriden...")

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(None)

        print(f"Connecting to {self.host}:{self.port}")
        try:
            self.sock.connect((self.host, self.port))
            recorder_names = initialize(self.sock, self.mode)
            if not recorder_names:
                self.live = False
                raise Exception(f"Communication refused to {self}")
        except (ConnectionRefusedError, OSError):
            self.live = False
            self.sock.close()
            #raise Exception(f"Connection refused to {self}")
        else:
            self.live = utils.live.LiveSocket(self.sock, async_read_entry)
            quality.register(self.mode, self.sock)

    def stop(self):
        self.live = None
        self.sock.close()
        quality.stop()
        print("Bye bye")
        import os, signal
        os.kill(os.getpid(), signal.SIGINT)

    def process_line(self, entry):
        if entry is None:
            print("ERROR: agent-interface: entry shouldn't be None")
            return

        try:
            process = self.processors[entry.name]
        except KeyError:
            print(f"INFO: {self.mode}: no processor registered for "
                  f"message type {entry.name}. Dropping.")
            print(entry)
            return

        import bdb
        try:
            if process is not None: process(entry) # otherwise: ignore
        except bdb.BdbQuit as e: raise e
        except Exception as e:
            print(f"WARNING: Failed to process entry {entry.name}: "
                  f"{e.__class__.__name__}: {e}")
            import sys, traceback
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_tb(exc_traceback, file=sys.stdout)
            print(entry)


# ---- #
