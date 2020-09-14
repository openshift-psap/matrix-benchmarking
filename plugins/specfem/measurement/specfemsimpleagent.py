import types


import measurement.agentinterface
from measurement.feedback import feedback

from . import specfem_baremetal as specfem_bm
from . import specfem_openshift as specfem_oc

SPECFEM_BUILD_PATH = "<from configure>"
NUM_WORKER_NODES = "<from configure>"
NUM_CORE_PER_NODE = "<from configure>"

def configure(plugin_cfg, machines):
    global SPECFEM_BUILD_PATH, NUM_WORKER_NODES, NUM_CORE_PER_NODE
    SPECFEM_BUILD_PATH = plugin_cfg['build_path']
    NUM_WORKER_NODES = int(plugin_cfg['num_worker_nodes'])
    NUM_CORE_PER_NODE = int(plugin_cfg['num_core_per_node'])

def get_or_default_param(params, key):
    DEFAULTS = {
        "nex": "-",
        "processes": "-",
        "threads": "-",
        "platform": "-"
    }

    if key == "nproc_per_worker":
        return int(NUM_CORE_PER_NODE/int(get_or_default_param(params, "threads")))
    
    try: return params[key]
    except KeyError:
        val = DEFAULTS[key]
        print(f"INFO: using default parameter for {key}: {val}")
        return val

class SpecfemSimpleAgent(measurement.agentinterface.AgentInterface):
    def setup(self):
        self.register_timing()
        self.register_feedback()
                
    def feedback(self, msg):
        src = "agent"
        self.feedback_table.add(0, src, msg.replace(", ", "||"))

    def remote_ctrl(self, _msg):
        msg = _msg[:-1].decode('ascii').strip()
        action, _, action_params = msg.partition(":")

        if action == "apply_settings":
            driver, _, params_str = action_params.partition(":")
   
            params = dict([kv.split("=") for kv in params_str.split(",")])

            if params.get("platform") == "openshift":
                specfem_oc.run_specfem(self, driver, params)
            else:
                specfem_bm.run_specfem(self, driver, params)

        elif action == "request" and action_params.startswith("reset"):
            if action_params.endswith("openshift"):
                specfem_oc.reset()
            elif action_params.endswith("baremetal") or action_params.endswith("podman"):
                specfem_bm.reset()
        else:
            print(f"remote_ctrl: unknown action '{action}/{action_params}' received ...")

    def register_feedback(self):
        self.feedback_table = \
            self.experiment.create_table([
            'feedback.msg_ts',
            'feedback.src',
            'feedback.msg',
        ])

        send_obj = types.SimpleNamespace()
        send_obj.send = self.remote_ctrl

        feedback.register("remote_ctrl", send_obj)

    def register_timing(self):
        self.timing_table = self.experiment.create_table([
            'timing.total_time'
        ])

def parse_and_save_timing(agent, output_solver_fname):
    with open(output_solver_fname) as output_f:
        for line in output_f.readlines():
            if not line.startswith(" Total elapsed time in seconds"): continue
            #  Total elapsed time in seconds =    269.54141061100000
            time_str = line.split("=")[-1].strip()
            total_time = int(float(time_str)) # ignore decimals
            break
        else:
            print("ERROR: failed to find the total elapsed time ...")
            return

    agent.timing_table.add(total_time=total_time)
    print(f"INFO: Execution time: {total_time}s")
    agent.feedback(f"Specfem finished after {total_time}s (={int(total_time/60)}min)")
