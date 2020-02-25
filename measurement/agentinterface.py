import socket
import struct
import asyncio
import collections
import threading
import re
from collections import deque
import types

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
        self.sock.settimeout(2)
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
        import bdb
        try:
            if process is not None: # otherwise: ignore
                process(entry)
        except bdb.BdbQuit as e: raise e
        except Exception as e:
            print(f"WARNING: Failed to process entry {entry.name}: {e.__class__.__name__}: {e}")
            import sys, traceback
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_tb(exc_traceback, file=sys.stdout)
            print(entry)


# ---- #

def register_entry_handlers(agent):
    register_agent_info(agent)
    register_quality_setting(agent)

    if agent.mode == "client":
        register_frame_stats(agent)
        register_frames_dropped(agent)

    elif agent.mode == "server":
        register_quality(agent)
        register_stream_channel_data(agent)

    elif agent.mode == "guest":
        register_guest_frame(agent)
        register_guest_streaming_info(agent)

def register_frames_dropped(agent):
    table = agent.experiment.create_table([
        'frames_dropped.msg_ts',
        'frames_dropped.count',
        'frames_dropped.total',
    ])

    table = agent.experiment.create_table([
        'frames_time_to_drop.msg_ts',
        'frames_time_to_drop.in_queue_time',
    ])

    drop_tracking_fmt = re.compile(r'drop frame after (\d+) in queue')

    drop_summary_fmt = re.compile(r'dropped (\d+) frames')

    total = 0
    def process(entry):
        nonlocal total
        if entry.msg.startswith("dropped"):
            dropped, = map(int, drop_summary_fmt.match(entry.msg).groups())
            total += dropped

            table.add(entry.time, dropped, total)
        elif entry.msg.startswith("drop frame"):
            in_queue_time, = map(int, drop_tracking_fmt.match(entry.msg).groups())

            table.add(entry.time, in_queue_time)
        else:
            raise RuntimeError("Unknown 'frames_dropped' message")

    agent.processors["frames_dropped"] = process

def register_frame_stats(agent):
    stats_table = agent.experiment.create_table([
        'client.msg_ts',
        'client.mm_time',
        'client.frame_size',
        'client.creation_time',
        'client.decode_duration',
        'client.queue', 'client.queue_before',
        'client.keyframe',
        'client.framerate_actual', 'client.framerate_requested'
    ])

    info_table = agent.experiment.create_table([
        'new_frame.msg_ts',
        'new_frame.frame_size',
        'new_frame.keyframe'
    ])

    fmt_stats = re.compile(r'frame mm_time (\d+) size (\d+) creation time (\d+) decoded time (\d+) queue (\d+) before (\d+) keyframe (\d+)')
    fmt_info = re.compile(r'frame size (\d+) keyframe (\d+)')

    framerate_state = init_framerate_state()

    def process_stats(entry):
        match = fmt_stats.match(entry.msg)
        if match is None: return

        mm_time, frame_size, creation_time, decode_duration, queue, before, keyframe = \
            map(int, match.groups())

        creation_time /= 1000000
        decode_duration /= 1000000

        framerate = process_framerate(framerate_state, entry.time)

        stats_table.add(entry.time, mm_time, frame_size, creation_time,
                        decode_duration, queue, before, keyframe, *framerate.values())

    def process_info(entry):
        frame_size, keyframe= map(int, fmt_info.match(entry.msg).groups())

        info_table.add(entry.time, frame_size, keyframe)

    agent.processors["frames_stats"] = process_stats
    agent.processors["frames_info"] = process_info


def register_quality(agent):
    agent.quality_table = \
        agent.experiment.create_table([
            'quality.msg_ts',
            'quality.src',
            'quality.msg',
        ])

    def process(entry):
        src, _, msg = entry.msg.partition(": ")

        agent.quality_table.add(entry.time, src, msg.replace(", ", "||"))
        if msg.startswith("#"):
            msg = msg[:20] + "..." + msg[-20:]
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
        'host.framerate_actual', 'host.framerate_requested'
    ])

    framerate_state = init_framerate_state()

    fmt = re.compile(r'Stream data packet size (\d+) mm_time (\d+)')
    def process(entry):
        frame_size, mm_time = fmt.match(entry.msg).groups()

        framerate = process_framerate(framerate_state, entry.time)

        table.add(entry.time, int(frame_size), int(mm_time), *framerate.values())

    agent.processors["stream_channel_data"] = process
    agent.processors["stream_device_data"] = None # ignore, identical to above

def register_guest_streaming_info(agent):
    def process(entry):
        info_type, _, info_msg = entry.msg.partition(": ")
        if info_type == "resolution":
            print("Guest streaming resolution:", info_msg)
            quality.send_str("guest:"+entry.msg)
        else:
            print("Unknown streaming_info message:", entry.msg)

    agent.processors["streaming_info"] = process

def time_length(pipe):
    l = pipe[-1][0] - pipe[0][0]

    return (pipe[-1][0] - pipe[0][0]) / 1000000

def init_framerate_state():
    state = collections.namedtuple('FramerateState', 'pipe prev target')
    state.pipe = deque()
    state.prev = None
    state.target = target_framerate

    return state

PIPE_MIN_TIME_LENGTH = 2 #s

PIPE_MAX_TIME_LENGTH = 5 #s
target_framerate = None

def process_framerate(state, time):
    import statistics
    prev = state.prev
    ts = state.prev = time

    def ret(framerate):
        return dict(framerate_actual=framerate,
                    framerate_requested=target_framerate)

    if target_framerate != state.target:
        state.prev = None
        state.pipe = deque()
        state.target = target_framerate
        return ret(None)

    if prev is None:
        return ret(None)

    delta = (ts - prev) / 1000000
    fps = 1 / delta

    state.pipe.append((ts, fps))

    if time_length(state.pipe) < PIPE_MIN_TIME_LENGTH:
        return ret(None)

    while time_length(state.pipe) >= PIPE_MAX_TIME_LENGTH:
        state.pipe.popleft()

    mean = statistics.mean((p[1] for p in state.pipe))

    return ret(mean)

def register_quality_setting(agent):
    def process(entry):
        print(f"{agent.mode}: Agent info received: '{entry.msg}'")
        if entry.msg.startswith("encoding:framerate:"):
            global target_framerate
            target_framerate = int(entry.msg.rpartition(":")[-1])
        else:
            print(f"{agent.mode}: quality setting '{entry.msg}' not recognized...")

    agent.processors["quality_setting"] = process

def register_guest_frame(agent):
    capture_table = agent.experiment.create_table([
        'guest_capt.msg_ts',
        'guest_capt.capture_duration',
        'guest_capt.push_duration'])

    encode_table = agent.experiment.create_table([
        'guest.msg_ts',
        'guest.frame_size',
        'guest.sleep_duration',
        'guest.pull_duration',
        'guest.send_duration',
        'guest.key_frame',
        'guest.framerate_actual', 'guest.framerate_requested'
    ])

    framerate_state = init_framerate_state()

    def CaptureState():
        s = collections.namedtuple('CaptureState',
                                   'prev_time capture push')
        s.prev_time = None
        return s

    def resetEncodeState(s):
        s.start = None
        s.prev_time = None
        s.send = None
        s.sleep = None
        s.keyframe = 0
        s.frame_bytes = None

    encode_state = collections.namedtuple('State', 'start frame_bytes prev_time '
                                       'send sleep pull '
                                       'width height codec keyframe')
    resetEncodeState(encode_state)
    capture_state = CaptureState()

    frame_fmt = re.compile(r'Frame of (\d+) bytes')

    def process(entry):
        time = entry.time

        verb = entry.msg.split()[0]

        if "." in verb: mode, verb = verb.split(".")
        else: mode = None

        if entry.name == "frame" and mode is None and verb == 'Capturing':
            encode_state.start = time
            return

        if mode == "Capture" and verb == "capturing":
            capture_state.prev_time = time
            return

        def encode_dist():  return (time - encode_state.prev_time) / 1000000
        def capture_dist():  return (time - capture_state.prev_time) / 1000000
        def dist(start, stop): return (stop - start) / 1000000

        if mode == "Capture":
            if capture_state.prev_time is None:
                return # partial state, skip it

            elif verb == "pushing":
                capture_state.capture = capture_dist()

            elif verb == "done":
                capture_state.push = capture_dist()

                capture_table.add(
                    msg_ts = time,
                    capture_duration = capture_state.capture,
                    push_duration = capture_state.push)
                #print("      |", " "*10, "---")
                capture_state.prev_time = None
                return
            else:
                print(f"WARNING: agentinterface: unknown Capture verb: {verb}")
                return
            capture_state.prev_time = time
            return

        elif mode == "Encode":
            if encode_state.start is None:
                return # partial state, skip it
            if verb == "pulling":
                pass # just to set encode_state.prev_time = time
            elif verb == "sleeping":
                encode_state.pull = encode_dist()
            elif verb == "done":
                encode_state.sleep = encode_dist()


            else:
                print(f"WARNING: agentinterface: unknown Encode verb: {verb}")
                return
            encode_state.prev_time = time
        else:
            if encode_state.start is None: return # partial state, skip it

            if verb == 'Capturing': pass
            elif verb == 'Captured': pass
            elif verb == 'Frame':
                encode_state.frame_bytes = int(frame_fmt.match(entry.msg).group(1))

            elif verb == 'Keyframe':
                encode_state.keyframe = 1

            elif verb == 'Sent':
                encode_state.send = encode_dist()

                framerate = process_framerate(framerate_state, time)

                encode_table.add(
                    msg_ts = time,
                    frame_size = encode_state.frame_bytes,
                    key_frame = encode_state.keyframe,

                    pull_duration = encode_state.pull,
                    sleep_duration = encode_state.sleep,
                    send_duration = encode_state.send,

                    **framerate)

                resetEncodeState(encode_state)
            else:
                print(f"WARNING: agentinterface: unknown Main verb: {verb}")
                return
            encode_state.prev_time = time

    agent.processors["frame"] = process
    agent.processors["gst_frame"] = process
    agent.processors["nv_frame"] = process
