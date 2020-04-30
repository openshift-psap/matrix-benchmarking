import re, collections
from collections import deque

import statistics

import measurement.hot_connect
import measurement.agentinterface
from measurement.feedback import feedback

class SpiceAgentInterface(measurement.agentinterface.AgentInterface):
    def setup(self):
        register_agent_info(self)
        register_feedback_setting(self)

        if self.mode == "client":
            register_frame_stats(self)
            register_frames_dropped(self)

        elif self.mode == "server":
            register_feedback(self)
            register_stream_channel_data(self)

        elif self.mode == "guest":
            register_guest_frame(self)
            register_guest_streaming_info(self)


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


def register_feedback(agent):
    agent.feedback_table = \
        agent.experiment.create_table([
            'feedback.msg_ts',
            'feedback.src',
            'feedback.msg',
        ])

    def process(entry):
        src, _, msg = entry.msg.partition(": ")

        agent.feedback_table.add(entry.time, src, msg.replace(", ", "||"))
        if msg.startswith("#"):
            msg = msg[:20] + "..." + msg[-20:]
        print(f"Feedback received: '{src}' says '{msg}'")

    agent.processors["feedback_interface"] = process


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
            feedback.send_str("guest:"+entry.msg)
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

def register_feedback_setting(agent):
    def process(entry):
        print(f"{agent.mode}: Agent info received: '{entry.msg}'")
        if entry.msg.startswith("encoding:framerate:"):
            global target_framerate
            target_framerate = int(entry.msg.rpartition(":")[-1])
        else:
            print(f"{agent.mode}: feedback setting '{entry.msg}' not recognized...")

    agent.processors["feedback_setting"] = process

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
