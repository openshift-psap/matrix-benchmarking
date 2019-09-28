import socket
import struct
import asyncio
import collections
import threading
import re

import measurement
import measurement.hot_connect
import utils.live

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

        self.processors = {}

        self.live = None

        self.host = cfg.get("host", "localhost")
        self.port = cfg["port"]
        self.mode = cfg["mode"]

    def __str__(self):
        return f"AgentInterface:{self.mode}<{self.host}:{self.port}>"

    def setup(self):
        register_entry_handlers(self)

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

    def process_line(self, entry):
        if entry is None:
            print("ERROR: agent-interface: entry shouldn't be None")
            return

        try:
            process = self.processors[entry.name]
        except KeyError:
            print(f"INFO: {self.mode}: no processor registered for message type {entry.name}. Dropping.")
            print(entry)
            return

        try:
            if process is not None: # otherwise: ignore
                process(entry)
        except Exception as e:
            print(f"WARNING: Failed to process entry {entry.name}: {e.__class__.__name__}: {e}")
            print(entry)


# ---- #

def register_entry_handlers(agent):
    register_agent_info(agent)

    if agent.mode == "client":
        register_frame_stats(agent)

    elif agent.mode == "server":
        register_quality(agent)
        register_stream_channel_data(agent)

    elif agent.mode == "guest":
        register_guest_frame(agent)


def register_frame_stats(agent):
    table = agent.experiment.create_table([
        'client.msg_ts',
        'client.mm_time',
        'client.frame_size',
        'client.time',
        'client.decode_duration',
        'client.queue',
    ])

    fmt = re.compile(r'frame mm_time (\d+) size (\d+) creation time (\d+) decoded time (\d+) queue (\d+) before (\d+)')
    def process(entry):


        mm_time, frame_size, time, decode_duration, queue, before = \
            map(int, fmt.match(entry.msg).groups())

        time /= 1000000
        decode_duration /= 1000000

        table.add(entry.time, mm_time, frame_size, time, decode_duration, queue)

    agent.processors["frames_stats"] = process


def register_quality(agent):
    agent.quality_table = \
        agent.experiment.create_table([
            'quality.msg_ts',
            'quality.src',
            'quality.msg',
        ])

    def process(entry):
        src, _, msg = entry.msg.partition(": ")

        agent.quality_table.add(entry.time, src, msg.replace(",", "||"))

        print(f"Quality received: '{src}' says '{msg}'")

    agent.processors["quality_interface"] = process


def register_agent_info(agent):
    def process(entry):
        print(f"{agent.mode}: Agent info received: '{entry.msg}'")
        if entry.msg.startswith("pid: "):
            pid = int(entry.msg.partition(" ")[-1])
            measurement.hot_connect.attach_to_pid(agent.experiment, agent.mode, pid)
        else:
            print("{agent.mode}: info not recognized...")

    agent.processors["agent_info"] = process


def register_stream_channel_data(agent):
    table = agent.experiment.create_table([
        'host.msg_ts',
        'host.frame_size',
        'host.mm_time',
    ])

    fmt = re.compile(r'Stream data packet size (\d+) mm_time (\d+)')
    def process(entry):
        frame_size, mm_time = fmt.match(entry.msg).groups()

        table.add(entry.time, int(frame_size), int(mm_time))

    agent.processors["stream_channel_data"] = process
    agent.processors["stream_device_data"] = None # ignore, identical to above

def register_guest_frame(agent):
    table = agent.experiment.create_table([
        'guest.msg_ts',
        'guest.time',
        'guest.frame_size',
        'guest.capture_duration',
        'guest.encode_duration',
        'guest.send_duration',
    ])

    state = collections.namedtuple('State', 'start captured sent frame_bytes encoded'
                                   'width height codec')
    state.start = None
    frame_fmt = re.compile(r'Frame of (\d+) bytes')
    def process(entry):
        time = entry.time

        verb = entry.msg.split()[0]

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
            state.frame_bytes = int(frame_fmt.match(entry.msg).group(1))

        elif verb == 'Sent':
            state.sent = time

            if state.start is None: return # partial state, skip it

            table.add(time,
                      state.start / 1000000, state.frame_bytes,
                      (state.captured - state.start) / 1000000,
                      (state.encoded - state.captured) / 1000000,
                      (state.sent - state.encoded) / 1000000)

    agent.processors["frame"] = process
