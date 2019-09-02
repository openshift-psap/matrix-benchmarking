import socket
import struct
import asyncio
import collections
import threading

import measurement
import utils.live
import ui.dataview

#---

def sock_read_string(sock):
    string = ""

    while True:
        c = sock.recv(1).decode("ascii")
        if c == '\0':
            return string
        if not c:
            return

        string += c

def sock_read_uint64(sock):
    data = sock.recv(8)
    return struct.unpack("L", data)[0]


async def async_read_string(reader):
   string = ""
   while True:
       data = await reader.read(1)
       c = data.decode("ascii")
       if c == '\0':
           return string
       if not c:
            return
       string += c

async def async_read_uint64(reader):
    data = b""
    to_read = 8
    while len(data) < 8:
        d = await reader.read(to_read)
        if not d:
            return

        data += d
        to_read -= len(d)
        if to_read != 0: print("partial:", len(d))
    try:
        return struct.unpack("L", data)[0]
    except:
        pass


Entry = collections.namedtuple("RecorderEntry", "name fmt where timestamp args")
async def async_read_entry(reader):
    entry = Entry(
        name = await async_read_string(reader),
        fmt = await async_read_string(reader),
        where = await async_read_string(reader),
        timestamp = await async_read_uint64(reader),
        args = [await async_read_uint64(reader) for _ in range(4)])

    if None in entry: return False

    return entry

#---

def initialize(sock, mode):
    nb_recorders = sock_read_uint64(sock)

    if nb_recorders == 0:
        return None

    names = [sock_read_string(sock) for _ in range(nb_recorders)]

    # enable all the recorders
    for name in names:
        sock.sendall(struct.pack("I", 1))

    print(f"{mode}: received {nb_recorders} recorders: {', '.join(names)}")

    return names

#---
ENABLE_STDIN_QUALITY = False

class ConsoleQuality():
    def __init__(self):
        self.agents = {}
        self.running = None
        if not ENABLE_STDIN_QUALITY:
            return

        self.thr = threading.Thread(target=self.thread_routine)
        self.thr.daemon = True
        self.thr.start()

    def send_str(self, line):
        print("Quality Input: >>", line)

        mode, found, msg = line.partition(":")
        if not found \
           or not mode in self.agents \
           or "\0" in msg \
           or len(msg) > 127:
            print("Invalid message. Valid modes:", ",".join(self.agents.keys()))
            return
        self.agents[mode].send((msg+"\0").encode("ascii"))

    def thread_routine(self):
        self.running = True
        print("Quality Input: Running")

        while self.running:
            try:
                line = input()
                if line == "bye":
                    break
            except EOFError:
                break
            except Exception as e:
                print("Quality Input: error:", e)
                continue

            self.send_str(line)

        self.running = False
        print("Quality Input: done")

    def register(self, name, sock):
        self.agents[name] = sock

    def stop(self):
        if not self.running: return
        self.running = False

quality = ConsoleQuality()

class AgentInterface(measurement.Measurement):
    def __init__(self, cfg, experiment):
        measurement.Measurement.__init__(self, experiment)

        self.tables = {}
        self.states = {}

        self.live = None

        self.host = cfg.get("host", "localhost")
        self.port = cfg["port"]
        self.mode = cfg["mode"]

    def __str__(self):
        return f"AgentInterface:{self.mode}<{self.host}:{self.port}>"

    def setup(self):
        if self.mode == "client":
            self.tables["frames_stats"] = \
                self.experiment.create_table([
                    'client.mm_time',
                    'client.frame_size',
                    'client.time',
                    'client.decode_duration',
                    'client.queue',
                ])
            self.states["frames_stats"] = {}
            self.states["frames_stats"]["first_entry"] = None

        if self.mode == "server":
            self.quality_table = \
                self.experiment.create_table([
                    'quality.ts',
                    'quality.src',
                    'quality.msg',
                    ])

            self.tables["stream_channel_data"] = \
                self.experiment.create_table([
                    'host.frame_size',
                    'host.mm_time',
                ])
            self.states["stream_channel_data"] = {}

        if self.mode == "guest":
            self.table = self.experiment.create_table([
                'guest.time',
                'guest.frame_size',
                'guest.capture_duration',
                'guest.encode_duration',
                'guest.send_duration',
            ])
            self.state = collections.namedtuple('State', 'start captured sent frame_bytes encoded'
                                                'width height codec')
            self.state.start = None

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("Connecting to", self.port)
        try:
            self.sock.connect((self.host, self.port))
            recorder_names = initialize(self.sock, self.mode)
            if not recorder_names:
                self.live = False
                raise Exception(f"Communication refused by the AgentInterface on {self.host}:{self.port} ({self.mode})")
        except ConnectionRefusedError:
            self.live = False
            raise Exception(f"Cannot connect to the AgentInterface on {self.host}:{self.port} ({self.mode})")

        self.live = utils.live.LiveSocket(self.sock, async_read_entry)

        quality.register(self.mode, self.sock)

    def stop(self):
        self.live = None
        self.sock.close()

        quality.stop()

    def save_guest_frames(self, state, entry):
        state = self.state

        time = entry.timestamp
        filename, lineno, *msg = entry.fmt.split(":")
        msg = ":".join(msg)

        verb = msg.split()[0]

        if verb == 'Capturing':
            state.start = time
            state.captured = None
            state.sent = None
            state.frame_bytes = None
            state.encoded = None
        elif verb == 'Encoding':
            state.captured = time
        elif verb == 'Captured':
            # old logs do not have encoding
            if state.captured is None:
                state.captured = time
            state.encoded = time
        elif verb == 'Frame':
            state.frame_bytes = entry.args[0]

        elif verb == 'Sent':
            state.sent = time

            if state.start is None: return # partial state, skip it
            self.table.add(state.start / 1000000, state.frame_bytes,
                           (state.captured - state.start) / 1000000,
                           (state.encoded - state.captured) / 1000000,
                           (state.sent - state.encoded) / 1000000)

        elif verb == 'Started':
            if "new stream wXh" in msg:
                state.width, state.height, state.codec, _ = entry.args
                quality.send_str(f"guest:New stream started: {state.width}x{state.height}, codec type {state.codec}")

    def save_frames_stats(self, state, recorder_entry):
        if not state["first_entry"]:
            state["first_entry"] = recorder_entry
            return

        first_entry = state["first_entry"]

        assert first_entry.timestamp == recorder_entry.timestamp
        assert not recorder_entry.where
        assert not recorder_entry.fmt

        mm_time, frame_size, time, decode_duration = first_entry.args
        queue = recorder_entry.args[0]

        time /= 1000000
        decode_duration /= 1000000

        self.tables[recorder_entry.name].add(mm_time, frame_size, time, decode_duration, queue)
        state["first_entry"] = None

    def save_stream_channel_data(self, state, recorder_entry):
        frame_size, mm_time = recorder_entry.args[:2]

        self.tables["stream_channel_data"].add(frame_size, mm_time)

    def process_line(self, recorder_entry):
        if recorder_entry.name == "frame":
            self.save_guest_frames(self.states, recorder_entry)

        elif recorder_entry.name == "quality_interface":
            src = recorder_entry.fmt.rpartition(":")[-1]
            msg = recorder_entry.where.replace(",", "||")

            self.quality_table.add(recorder_entry.timestamp, src, msg)

            print(f"Quality received: '{src}' says '{msg}'")
        if recorder_entry.name == "frames_stats":
            return self.save_frames_stats(self.states["frames_stats"],
                                          recorder_entry)
        elif recorder_entry.name == "stream_channel_data":
            return self.save_stream_channel_data(self.states["stream_channel_data"],
                                                 recorder_entry)
