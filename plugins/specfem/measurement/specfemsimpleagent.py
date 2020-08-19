import re, collections, types, os, socket, subprocess, math
from collections import deque

import statistics

import measurement.hot_connect
import measurement.agentinterface
from measurement.feedback import feedback

HOSTNAME = socket.gethostname()
SPECFEM_BUILD_PATH = "<from configure>"
NUM_WORKER_NODES = "<from configure>"
NUM_CORE_PER_NODE = "<from configure>"

CONFIGURE_SH = """
DATA_DIR="/data/kevin"
BUILD_DIR="$DATA_DIR/specfem3d_globe"
SHARED_DIR="/mnt/fsx/kevin"
SHARED_SPECFEM="$SHARED_DIR/specfem"
"""

# ssh -N -L localhost:1230:f12-h17-b01-5039ms.rdu2.scalelab.redhat.com:1230 root@f12-h17-b01-5039ms.rdu2.scalelab.redhat.com

BUILD_AND_RUN_SH = """
MPIRUN_CMD="mpirun --report-child-jobs-separately --allow-run-as-root --mca btl ^openib -mca pml ob1 --mca btl_tcp_if_include enp1s0f0"

cp "$BUILD_DIR"/run_{mesher,solver}.sh "$SHARED_SPECFEM"

echo "Building the mesher ..."
if ! make mesh -j8 >/dev/null 2>/dev/null; then
  echo Mesher build failed ...
  exit 1
fi
echo "Solver built."

cp {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xmeshfem3D

rm -rf "$SHARED_SPECFEM"/{DATABASES_MPI,OUTPUT_FILES}/*

cd "$SHARED_SPECFEM"

echo "Running the mesher ..."
$MPIRUN_CMD -np $SPECFEM_MPI_NPROC --hostfile $BUILD_DIR/hostfile.mpi bash ./run_mesher.sh |& grep -v "Warning: Permanently added"
echo "Mesher execution done."

cp {"$SHARED_SPECFEM","$BUILD_DIR"}/OUTPUT_FILES/values_from_mesher.h 

cd "$BUILD_DIR"

echo "Building the solver ..."
if !make spec -j8 >/dev/null 2>/dev/null; then
  echo Build failed ...
  exit 1
fi
echo "Solver built."

cp {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xspecfem3D

cd "$SHARED_SPECFEM"

$MPIRUN_CMD -np $SPECFEM_MPI_NPROC --hostfile $BUILD_DIR/hostfile.mpi bash ./run_solver.sh |& grep -v "Warning: Permanently added"
echo "Solver execution done."

cp {"$SHARED_SPECFEM","$BUILD_DIR"}/OUTPUT_FILES/output_solver.txt
"""

RUN_MESHER_SH = """
WORK_DIR=/data/kevin/specfem/$OMPI_COMM_WORLD_NODE_RANK

rm -rf "$WORK_DIR/"
mkdir -p "$WORK_DIR/"

cp ./ "$WORK_DIR/" -rf

cd "$WORK_DIR/"

./bin/xmeshfem3D "$@"

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  cp OUTPUT_FILES/{values_from_mesher.h,output_mesher.txt} "$SHARED_SPECFEM/OUTPUT_FILES/"
fi

cp -f DATABASES_MPI/* "$SHARED_SPECFEM/DATABASES_MPI/"

echo Done $OMPI_COMM_WORLD_RANK
"""

RUN_SOLVER_SH = """
WORK_DIR=/data/kevin/specfem/$OMPI_COMM_WORLD_NODE_RANK

cp ./bin/xspecfem3D "$WORK_DIR/bin/xspecfem3D" -r

cp DATABASES_MPI/* "$WORK_DIR/DATABASES_MPI/"

cd "$WORK_DIR"
./bin/xspecfem3D "$@"

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  cp OUTPUT_FILES/output_solver.txt "$SHARED_SPECFEM/OUTPUT_FILES/"
fi

echo Done $OMPI_COMM_WORLD_RANK
"""

def configure(plugin_cfg, machines):
    global SPECFEM_BUILD_PATH, NUM_WORKER_NODES, NUM_CORE_PER_NODE
    SPECFEM_BUILD_PATH = plugin_cfg['build_path']
    NUM_WORKER_NODES = int(plugin_cfg['num_worker_nodes'])
    NUM_CORE_PER_NODE = int(plugin_cfg['num_core_per_node'])
    
    prepare_system()
    
def prepare_system():
    with open(f"{SPECFEM_BUILD_PATH}/build_and_run.sh", "w") as script_f:
        print("#! /bin/bash", file=script_f)
        print("set -ex", file=script_f)
        print(CONFIGURE_SH, file=script_f)
        print(BUILD_AND_RUN_SH, file=script_f)

    with open(f"{SPECFEM_BUILD_PATH}/run_mesher.sh", "w") as script_f:
        print("#! /bin/bash", file=script_f)
        print("set -e", file=script_f)
        print(CONFIGURE_SH, file=script_f)
        print(RUN_MESHER_SH, file=script_f)

    with open(f"{SPECFEM_BUILD_PATH}/run_solver.sh", "w") as script_f:
        print("#! /bin/bash", file=script_f)
        print("set -e", file=script_f)
        print(CONFIGURE_SH, file=script_f)
        print(RUN_SOLVER_SH, file=script_f)        
        
def prepare_mpi_hostfile(nproc, nproc_per_worker):
    print(f"INFO: running with nproc={nproc}, nproc_per_worker={nproc_per_worker}")
    with open(f"{SPECFEM_BUILD_PATH}/hostfile.mpi", "w") as hostfile_f:
        print(f"manager slots={nproc_per_worker}", file=hostfile_f)
        for i in range(NUM_WORKER_NODES):
            print(f"worker{i} slots={nproc_per_worker}", file=hostfile_f)
                
def specfem_set_par(key, new_val):
    changed = 1 # buffer changes to avoid touching Par_file without changing anything
    par_file_lines = []
    par_filename = f"{SPECFEM_BUILD_PATH}/DATA/Par_file"
    with open(par_filename) as par_f:
        for line in par_f.readlines():
            if not line.strip() or line.startswith("#"):
                par_file_lines.append(line)
                continue

            line_key, old_val = "".join(line.split()).partition("#")[0].split("=")
            if line_key == key:
                if old_val == str(new_val):
                    print(f"INFO: Specfem: set {key} = {new_val} already set.")
                else:
                    print(f"INFO: Specfem: set {key} = {new_val} (was {old_val})")
                    line = line.replace(f"= {old_val}", f"= {new_val}")
                    changed += 1
            par_file_lines.append(line)

    if not changed:
        return

    
    with open(par_filename, "w") as par_f:
        for line in par_file_lines:
            par_f.write(line)


def get_or_default_param(params, key):
    DEFAULTS = {
        "nex": "16",
        "nodes": "4",
        "cores": "4",
    }

    if key == "nproc_per_worker":
        return int(int(get_or_default_param(params, "cores"))/NUM_CORE_PER_NODE)
    
    try: return params[key]
    except KeyError:
        val = DEFAULTS[key]
        print(f"INFO: using default parameter for {key}: {val}")
        return val

class SpecfemSimpleAgent(measurement.agentinterface.AgentInterface):
    def setup(self):
        self.register_timing()
        self.register_feedback()
        
        prepare_system()
        
    def feedback(self, msg):
        src = "specfem"
        self.feedback_table.add(0, src, msg.replace(", ", "||"))

    def remote_ctrl(self, _msg):
        msg = _msg[:-1].decode('ascii').strip()
        action, _, action_params = msg.partition(":")

        if action == "apply_settings":
            driver, _, params_str = action_params.partition(":")
   
            params = dict([kv.split("=") for kv in params_str.split(",")])

            self.specfem_run(driver, params)

        elif action == "request" and action_params == "reset":
            print("pkill xspecfem3D")
            os.system("pkill xspecfem3D")
            print("pkill xspecfem3D --> done")
            pass 
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

    def specfem_parse_and_save_timing(self):
        with open(f"{SPECFEM_BUILD_PATH}/OUTPUT_FILES/output_solver.txt") as output_f:
            for line in output_f.readlines():
                if not line.startswith(" Total elapsed time in seconds"): continue
                #  Total elapsed time in seconds =    269.54141061100000
                time_str = line.split("=")[-1].strip()
                time = int(float(time_str)) # ignore decimals
                break
            else:
                print("ERROR: failed to find the total elapsed time ...")
                return False
            
        self.timing_table.add(total_time=time)
        return time
    
    def specfem_run(self, driver, params):
        try: os.remove(f"{SPECFEM_BUILD_PATH}/OUTPUT_FILES/output_solver.txt")
        except FileNotFoundError: pass # ignore
        
        nex = get_or_default_param(params, "nex")
        specfem_set_par("NEX_XI", nex)
        specfem_set_par("NEX_ETA", nex)
    
        nproc_param = int(get_or_default_param(params, "nodes"))
        nproc = int(math.sqrt(nproc_param))
        specfem_set_par("NPROC_XI", nproc)
        specfem_set_par("NPROC_ETA", nproc)
    
        nproc_per_worker = int(get_or_default_param(params, "nproc_per_worker"))
        prepare_mpi_hostfile(nproc, nproc_per_worker)
        
        num_threads = get_or_default_param(params, "cores")

        cwd = SPECFEM_BUILD_PATH
        cmd = ["env",
               f"OMP_NUM_THREADS={num_threads}",
               f"SPECFEM_MPI_NPROC={nproc_param}",
               "bash", "./build_and_run.sh"]
        print(f"INFO: running '{' '.join(cmd)}' in '{cwd}'")

        process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE)
        process.wait()

        errcode = process.returncode
        output = process.communicate()[0].decode("utf-8")
        
        for line in output.split("\n"):
            self.feedback("| " + line)
            
        if errcode != 0:
            print(f"ERROR: Specfem finished with errcode={errcode}")
            print("8<--8<--8<--")
            print(output)
            print("8<--8<--8<--")
            self.feedback(f"Specfem finished errcode={errcode}")
            return
        
        print(f"INFO: Specfem finished successfully")

        timing = self.specfem_parse_and_save_timing()
        if timing is not False:
            print(f"INFO: Execution time: {timing}s")
        else:
            print(f"ERROR: failed to parse the final timing values")
            print("8<--8<--8<--")
            print(output)
            print("8<--8<--8<--")
