import re, collections, types, os, socket
from collections import deque
import subprocess

import statistics

import measurement.hot_connect
import measurement.agentinterface
from measurement.feedback import feedback

BIN_PATH = None

BINARIES = {
    "8byte": "matmul_8byte_aligned",
    "double": "matmul_double_aligned",
    "cache_line": "matmul_cache_line_aligned",
    "page_size": "matmul_page_size_aligned",
    "none": "matmul_unaligned",
}

def configure(plugin_cfg, machines):
    global BIN_PATH
    BIN_PATH = plugin_cfg['bin_path']

def run_alignment(params):
    size = int(params['matrix_size'])
    threads = int(params['threads'])
    num_iterations = int(params['num_iterations'])
    binary = BIN_PATH+"/"+BINARIES[params['alignment']]
                       
    cmd = ['env', f'OMP_NUM_THREADS={threads}', binary, str(size), str(size), str(size),
           str(num_iterations)]
    print(f"INFO: run_alignement '{' '.join(cmd)}'")

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    process.wait()

    return process.returncode, process.communicate()[0].decode("utf-8")

class AlignmentAgentInterface(measurement.agentinterface.AgentInterface):
    def setup(self):
        self.final_timing_register()
        self.register_feedback()
        
        obj = types.SimpleNamespace()
        obj.send = self.remote_ctrl

        feedback.register("remote_ctrl", obj)
        
        self.it_cnt = 1

    def feedback(self, msg):
        src = "alignment"
        self.feedback_table.add(0, src, msg.replace(", ", "||"))

    def add_to_feedback(self, msg):
        src = "agent"
        self.feedback_table.add(0, src, msg.replace(", ", "||"))

    def remote_ctrl(self, _msg):
        msg = _msg[:-1].decode('ascii').strip()
        action, _, action_params = msg.partition(":")

        if action == "apply_settings":
            driver, _, params_str = action_params.partition(":")
            if driver != "Alignment":
                print(f"remote_ctrl:apply_settings: unknown driver '{driver}' requested ...")
                return

            self.feedback(f"Running the alignment benchmark with '{params_str}'")
            params = dict([kv.split("=") for kv in params_str.split(",")])

            errcode, output = run_alignment(params)
            for line in output.split("\n"):
                self.feedback("| " + line)

            if errcode != 0:
                print(f"ERROR: run_alignement finished with errcode={errcode}")
                print("8<--8<--8<--")
                print(output)
                print("8<--8<--8<--")
                self.feedback(f"Alignment benchmark finished errcode={errcode}")

            else:
                print(f"INFO: run_alignement finished successfully")

                if not self.final_timing_save(output):
                    print(f"ERROR: failed to parse the final timing values")
                    print("8<--8<--8<--")
                    print(output)
                    print("8<--8<--8<--")
                self.feedback(f"Alignment benchmark finished successfully :)")

        elif action == "request" and action_params == "reset":
            #print("Cannot reset ...")
            pass
        else:
            print(f"remote_ctrl: unknown action '{action}/{action_params}' received ...")

    def final_timing_register(self):
        self.timing_table = self.experiment.create_table([
            'timing.total', 'timing.per_chunk', 'timing.per_chunk_dev',
        ])

    def final_timing_save(self, output):
        total_time = None
        chunk_time = None
        chunk_dev = None
        for line in output.split("\n"):
            if "Total runtime" in line:
                if total_time is not None: return False
                    
                # '  >> Total runtime : 1.790 sec'
                total_time = float(line.split(":")[-1].split()[0])
                self.feedback(f"final timing: {line}")
                
            if "Average runtime overall" in line:
                if chunk_time is not None: return False
                # '  >> Average runtime overall (per run) : 0.22 +/- 0.01 sec'
                chunk_time, _, chunk_dev, _ = line.split(":")[-1].strip().split(" ")
                chunk_time = float(chunk_time)
                chunk_dev = float(chunk_dev)
                self.feedback(f"final timing: {line}")
                
        if None in (total_time, chunk_time, chunk_dev):
            return False
        

        
        self.timing_table.add(
            total = total_time,
            per_chunk = chunk_time,
            per_chunk_dev = chunk_dev,
        )

        return True
    
    def register_feedback(self):
        self.feedback_table = \
            self.experiment.create_table([
                'feedback.msg_ts',
                'feedback.src',
                'feedback.msg',
            ])
