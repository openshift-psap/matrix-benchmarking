import socket, struct, asyncio
import collections, time

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
def do_wait_collector(server):
    import threading, signal
    return True
    quit_signal = threading.Event()
    def quit(signo, _frame):
        print("")
        quit_signal.set()

    sigs = {}
    for sig in ('TERM', 'HUP', 'INT'):
        sig = getattr(signal, 'SIG'+sig)
        sigs[sig] = signal.getsignal(sig)
        signal.signal(sig, quit);

    while not (server.new_clients or server.current_clients):
        print("Waiting for the Performance Collector to connect ...")
        # cannot yet exit this loop ...
        time.sleep(1)
        if quit_signal.is_set():
            print("Interrupted while waiting for the perf collector.")
            return False

    for sig in ('TERM', 'HUP', 'INT'):
        sig = getattr(signal, 'SIG'+sig)
        signal.signal(sig, sigs[sig]);

    return True

def initialize(sock, mode, wait_collector):
    recorders = sock_readline(sock)
    if recorders is False:
        return False

    # eg: "Recorders: stream_channel_data;stream_device_data;"
    names = recorders[:-1].partition(": ")[-1].split(";")

    import agent.to_collector
    server = agent.to_collector.Server.current

    if wait_collector and not do_wait_collector(server):
        return

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
        self.live_async_connect = True
        self.host = cfg.get("host", "localhost")
        self.port = cfg["port"]
        self.mode = cfg["mode"]
        self.sock = None
        self.wait_collector = cfg.get("wait_collector", False)

        self.start()

    def __str__(self):
        return f"AgentInterface:{self.mode}<{self.host}:{self.port}>"

    def setup(self):
        raise NotImplementedError("Should be overriden...")

    def start(self):
        def async_connect():
            #print(f"Connecting to {self.host}:{self.port} ...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(None)

            try:
                self.sock.connect((self.host, self.port))
                recorder_names = initialize(self.sock, self.mode, self.wait_collector)
                if not recorder_names:
                    raise Exception(f"Communication refused to {self}")
            except (ConnectionRefusedError, OSError):
                self.sock.close()
                raise
            except Exception:
                self.sock.close()
                raise

            print(f"Connected to {self.host}:{self.port}!")
            quality.register(self.mode, self.sock)
            self.live_async_connect = False
            return self.sock

        self.live = utils.live.LiveSocket(None, async_read_entry,
                                          async_connect=async_connect,
                                          process=self.process_line)

    def stop(self):
        self.live = None
        if self.sock:
            self.sock.close()
        self.live_async_connect = True

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
