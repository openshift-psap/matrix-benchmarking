import re, collections, types, os
from collections import deque

import statistics

import measurement.hot_connect
import measurement.agentinterface
from measurement.quality import quality

SPECFEM_DIR = "/app"

def specfem_set_par(key, new_val):
    par_filename = f"{SPECFEM_DIR}/DATA/Par_file"
    with open(par_filename) as par_f:
        par_file_lines = par_f.readlines()

    changed = 0
    with open(par_filename, "w") as par_f:
        for line in par_file_lines:
            if not line.strip() or line.startswith("#"):
                par_f.write(line)
                continue

            line_key, old_val = "".join(line.split()).partition("#")[0].split("=")
            if line_key == key:
                print(f"INFO: Specfem: set {key} = {new_val} (was {old_val})")
                line = line.replace(f"= {old_val}", f"= {new_val}")
                changed += 1
            par_f.write(line)
    return changed

def get_or_default_param(params, key):
    DEFAULTS = {
        "machine": "laptop",
        "nex": "16",
        "threads": "4"
    }
    try: return params[key]
    except KeyError:
        val = DEFAULTS[key]
        print(f"INFO: using default parameter for {key}: {val}")
        return val

def fork_specfem(params):
    machine = get_or_default_param(params, "machine")
    if machine != "laptop":
        print(f"ERROR: cannot yet run specfem on {machine} ...")
        return

    nex = get_or_default_param(params, "nex")
    if (specfem_set_par("NEX_XI", nex) != 1 or
        specfem_set_par("NEX_ETA", nex) != 1):
        print(f"ERROR: failed to change NEX_XI/NEX_ETA param ...")
        return

    num_threads = get_or_default_param(params, "threads")

    cmd = f"export OMP_NUM_THREADS={num_threads}; \
cd {SPECFEM_DIR} && \
./rebuild.sh && \
./bin/xspecfem3D"
    print(f"INFO: run '{cmd}'")
    os.system(cmd)

class SpecfemAgentInterface(measurement.agentinterface.AgentInterface):
    def setup(self):
        register_agent_info(self)
        register_checkpoints(self)
        register_quality(self)

        obj = types.SimpleNamespace()
        obj.send = self.remote_ctrl

        quality.register("remote_ctrl", obj)

        self.it_cnt = 1

    def quality(self, entry):
        src = "specfem"
        self.quality_table.add(entry.time, src, entry.msg.replace(", ", "||"))

    def add_to_quality(self, msg):
        src = "agent"
        self.quality_table.add(0, src, msg.replace(", ", "||"))

    def remote_ctrl(self, _msg):
        msg = _msg[:-1].decode('ascii').strip()
        action, _, action_params = msg.partition(":")

        if action == "apply_settings":
            driver, _, params_str = action_params.partition(":")
            if driver != "Specfem3D":
                print(f"remote_ctrl:apply_settings: unknown driver '{driver}' requested ...")
                return
            params = dict([kv.split("=") for kv in params_str.split(",")])

            fork_specfem(params)

        elif action == "request" and action_params == "reset":
            print("RESET!!")

        else:
            print(f"remote_ctrl: unknown action '{action}/{action_params}' received ...")



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

def register_checkpoints(agent):
    loop_table = agent.experiment.create_table([
        'loop.msg_ts', 'loop.start', 'loop.it_pct',
        'loop.stages', 'loop.seismograms'
    ])

    general_table = agent.experiment.create_table([
        'general.msg_ts', 'general.start',
        'general.finish', 'general.specfem_time'
    ])

    general_state = collections.namedtuple('State', 'start')
    general_state.start = None

    loop_state = collections.namedtuple('State', 'start prev_time pct '
                                        'stages seismograms')
    loop_state.start = None
    def dist(time, prev_time):  return (time - prev_time) / 1000000

    def process_checkpoints(entry):
        time = entry.time
        loop_name, stage, *value = entry.msg.split(":")
        stage = stage.strip()
        if loop_name == "general":
            if stage == "start":
                general_state.start = time

            elif stage == "finish":
                if general_state.start is None: return # partial record ...

                specfem_time = int(value[0])
                agent.add_to_quality(f"execution time: {specfem_time}")

                general_table.add(
                    msg_ts = time,
                    start = general_state.start,
                    finish = dist(time, general_state.start),
                    specfem_time = specfem_time)

        elif loop_name == "time loop":
            if stage == "start":
                loop_state.start = time
                loop_state.prev_time = time
                it_idx = int(value[0])
                loop_state.it_pct = f"{it_idx/agent.it_cnt*100:.2f}"

            if loop_state.start is None:
                return # partial record ...

            if stage == "stages":
                loop_state.stages = dist(time, loop_state.prev_time)
            elif stage == "seismograms":
                loop_state.seismograms = dist(time, loop_state.prev_time)

                loop_table.add(
                    msg_ts = time,
                    start = loop_state.start,
                    it_pct = loop_state.it_pct,
                    stages = loop_state.stages,
                    seismograms = loop_state.seismograms)

            loop_state.prev_time = time

    def process_config(entry):
        print(entry.msg)
        if entry.msg.startswith("it_end"):
            agent.it_cnt = int(entry.msg.split(": ")[-1])

        agent.quality(entry)

    seismo_table = agent.experiment.create_table([
        'seismo.time', 'seismo.value_1', 'seismo.value_2', 'seismo.value_3'
    ])

    def process_seismo(entry):
        orient, time_value = entry.msg.split("|")
        time, value = time_value.split()
        orient = int(orient)
        time = float(time)
        value = float(value)

        values = {"value_1": None, "value_2": None, "value_3": None}
        values[f"value_{orient}"] = value
        seismo_table.add(time=time, **values)

    agent.processors["checkpoint"] = process_checkpoints

    agent.processors["config"] = process_config

    agent.processors["seismo"] = process_seismo

def register_agent_info(agent):
    def process(entry):
        print(f"{agent.mode}: Agent info received: '{entry.msg}'")
        if entry.msg.startswith("pid: "):
            pid = int(entry.msg.partition(" ")[-1])
            measurement.hot_connect.attach_to_pid(agent.experiment, agent.mode, pid)
        else:
            print("{agent.mode}: info not recognized...")

    agent.processors["agent_info"] = process
