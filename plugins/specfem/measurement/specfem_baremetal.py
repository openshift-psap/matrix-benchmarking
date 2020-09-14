import os, subprocess, math

from . import specfemsimpleagent

# must match plugin.specfem.scripts.install.sh
CONFIGURE_SH = """
DATA_DIR="/data/kpouget"
BUILD_DIR="$DATA_DIR/specfem3d_globe"
SHARED_DIR="$DATA_DIR/shared"
SHARED_SPECFEM="$SHARED_DIR/specfem"
PODMAN_BASE_IMAGE="quay.io/kpouget/specfem"
"""

# ssh -N -L localhost:1230:f12-h17-b01-5039ms.rdu2.scalelab.redhat.com:1230 root@f12-h17-b01-5039ms.rdu2.scalelab.redhat.com

BUILD_AND_RUN_SH = """
MPIRUN_CMD="mpirun --report-child-jobs-separately --allow-run-as-root --mca btl ^openib -mca pml ob1 --mca btl_tcp_if_include enp1s0f1 -np $SPECFEM_MPI_NPROC --hostfile $BUILD_DIR/hostfile.mpi"

if [ "$SPECFEM_USE_PODMAN" == "1" ]; then
  MPIRUN_CMD="$MPIRUN_CMD \
        --mca orte_tmpdir_base /tmp/podman-mpirun \
        --mca btl_base_warn_component_unused 0 \
        --mca btl_vader_single_copy_mechanism none \
    podman run --rm --env-host \
     -v /tmp/podman-mpirun:/tmp/podman-mpirun \
     -v $SHARED_SPECFEM:$SHARED_SPECFEM \
     --userns=keep-id --net=host --pid=host --ipc=host \
     --workdir=$SHARED_SPECFEM \
     $PODMAN_BASE_IMAGE"
   echo "$(date) Using PODMAN platform"
else
   echo "$(date) Using BAREMETAL platform"
fi

cp "$BUILD_DIR"/run_{mesher,solver}.sh "$SHARED_SPECFEM"
cp {"$BUILD_DIR","$SHARED_SPECFEM"}/DATA/Par_file

rm -f {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xspecfem3D {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xmeshfem3D

echo "$(date) Building the mesher ..."
cd "$BUILD_DIR"
make clean >/dev/null 2>/dev/null
if ! make mesh -j8 >/dev/null 2>/dev/null; then
  echo Mesher build failed ...
  exit 1
fi
echo "$(date) Mesher built."

cp {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xmeshfem3D

rm -rf "$SHARED_SPECFEM"/{DATABASES_MPI,OUTPUT_FILES}/
mkdir -p "$SHARED_SPECFEM"/{DATABASES_MPI,OUTPUT_FILES}/

cd "$SHARED_SPECFEM"

echo "$(date) Running the mesher ... $SPECFEM_CONFIG"
$MPIRUN_CMD  bash ./run_mesher.sh |& grep -v "Warning: Permanently added"
echo "$(date) Mesher execution done."

cp {"$SHARED_SPECFEM","$BUILD_DIR"}/OUTPUT_FILES/values_from_mesher.h 

cd "$BUILD_DIR"

echo "$(date) Building the solver ..."
if ! make spec -j8 >/dev/null 2>/dev/null; then
  echo $(date) Build failed ...
  exit 1
fi
echo "$(date) Solver built."

cp {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xspecfem3D
sync

cd "$SHARED_SPECFEM"
echo "$(date) Running the solver ... $SPECFEM_CONFIG"
$MPIRUN_CMD bash ./run_solver.sh |& grep -v "Warning: Permanently added"
echo "$(date) Solver execution done."

cp {"$SHARED_SPECFEM","$BUILD_DIR"}/OUTPUT_FILES/output_solver.txt
"""

RUN_MESHER_SH = """
WORK_DIR=/data/kevin/specfem/$OMPI_COMM_WORLD_NODE_RANK

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  set -x
  echo $(date) Preparing the work dir ... >&2
fi

rm -rf "$WORK_DIR/"
mkdir -p "$WORK_DIR/"

cp ./ "$WORK_DIR/" -rf

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo Running the mesher from "$WORK_DIR" ...
  echo $(date) Running the mesher >&2
fi

cd "$WORK_DIR/"
./bin/xmeshfem3D "$@"

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo $(date) Mesher done >&2
  rm -rf "$SHARED_SPECFEM/OUTPUT_FILES/"
  cp OUTPUT_FILES/ "$SHARED_SPECFEM/" -r
fi

cp -f DATABASES_MPI/* "$SHARED_SPECFEM/DATABASES_MPI/"

echo Mesher done $OMPI_COMM_WORLD_RANK
"""

RUN_SOLVER_SH = """
WORK_DIR=/data/kevin/specfem/$OMPI_COMM_WORLD_NODE_RANK

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  set -x

  echo $(date) Preparing the working directory ... >&2
fi

mkdir -p "$WORK_DIR/"
cp ./ "$WORK_DIR/" -rf

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo Running the solver from "$WORK_DIR" ...
  echo $(date) Running the solver ... >&2
fi

cd "$WORK_DIR"
./bin/xspecfem3D "$@"

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo $(date) Solver done. >&2

  cp OUTPUT_FILES/output_solver.txt "$SHARED_SPECFEM/OUTPUT_FILES/"
fi

echo Solver done $OMPI_COMM_WORLD_RANK
"""

first_run = True
def _prepare_system():
    with open(f"{specfemsimpleagent.SPECFEM_BUILD_PATH}/build_and_run.sh", "w") as script_f:
        print("#! /bin/bash", file=script_f)
        print("set -ex", file=script_f)
        print(CONFIGURE_SH, file=script_f)
        print(BUILD_AND_RUN_SH, file=script_f)

    with open(f"{specfemsimpleagent.SPECFEM_BUILD_PATH}/run_mesher.sh", "w") as script_f:
        print("#! /bin/bash", file=script_f)
        print("set -e", file=script_f)
        print(CONFIGURE_SH, file=script_f)
        print(RUN_MESHER_SH, file=script_f)

    with open(f"{specfemsimpleagent.SPECFEM_BUILD_PATH}/run_solver.sh", "w") as script_f:
        print("#! /bin/bash", file=script_f)
        print("set -e", file=script_f)
        print(CONFIGURE_SH, file=script_f)
        print(RUN_SOLVER_SH, file=script_f)        
        
def _prepare_mpi_hostfile(nproc, nproc_per_worker):
    with open(f"{specfemsimpleagent.SPECFEM_BUILD_PATH}/hostfile.mpi", "w") as hostfile_f:
        print(f"manager slots={nproc_per_worker}", file=hostfile_f)
        for i in range(1, specfemsimpleagent.NUM_WORKER_NODES):
            print(f"worker{i} slots={nproc_per_worker}", file=hostfile_f)
                
def _specfem_set_par(key, new_val):
    changed = 1 # buffer changes to avoid touching Par_file without changing anything
    par_file_lines = []
    par_filename = f"{specfemsimpleagent.SPECFEM_BUILD_PATH}/DATA/Par_file"
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

def reset():
    os.system("pkill xspecfem3D")
    

def run_specfem(agent, driver, params):
    global first_run
    if first_run:
        _prepare_system()
        first_run = False
    
    try: os.remove(f"{specfemsimpleagent.SPECFEM_BUILD_PATH}/OUTPUT_FILES/output_solver.txt")
    except FileNotFoundError: pass # ignore

    nex = get_or_default_param(params, "nex")
    _specfem_set_par("NEX_XI", nex)
    _specfem_set_par("NEX_ETA", nex)

    mpi_nproc = int(specfemsimpleagent.get_or_default_param(params, "processes"))
    specfem_nproc = int(math.sqrt(mpi_nproc))
    _specfem_set_par("NPROC_XI", specfem_nproc)
    _specfem_set_par("NPROC_ETA", specfem_nproc)

    nproc_per_worker = int(get_or_default_param(params, "nproc_per_worker"))
    msg = f"INFO: running with mpi_nproc={mpi_nproc}, nproc_per_worker={nproc_per_worker}"
    print(msg)
    agent.feedback(msg)
    _prepare_mpi_hostfile(mpi_nproc, nproc_per_worker)

    num_threads = get_or_default_param(params, "threads")

    use_podman = 1 if get_or_default_param(params, "platform") == "podman" else 0

    specfem_config = " | ".join([
        f"USE_PODMAN={use_podman}",
        f"MPI_NPROC={mpi_nproc}",
        f"MPI_SLOTS={nproc_per_worker}",
        f"OMP_THREADS={num_threads}",
        f"NEX={nex}"])

    agent.feedback("config: "+specfem_config)
    cwd = specfemsimpleagent.SPECFEM_BUILD_PATH
    cmd = ["env",
           f"OMP_NUM_THREADS={num_threads}",
           f"SPECFEM_MPI_NPROC={mpi_nproc}",
           f"SPECFEM_USE_PODMAN={use_podman}",
           f"SPECFEM_CONFIG={specfem_config}", # for logging
           "bash", "./build_and_run.sh"]
    msg = f"Running '{' '.join(cmd)}' in '{cwd}'"
    print(f"INFO:", msg)
    agent.feedback(msg)

    process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE)
    process.wait()

    errcode = process.returncode
    output = process.communicate()[0].decode("utf-8")

    for line in output.split("\n"):
        agent.feedback("| " + line)

    if errcode != 0:
        print(f"ERROR: Specfem finished with errcode={errcode}")
        print("8<--8<--8<--")
        print(output)
        print("8<--8<--8<--")
        agent.feedback(f"Specfem finished with errcode={errcode}")
        return

    print(f"INFO: Specfem finished successfully")

    success = parse_and_save_timing(agent, f"{specfemsimpleagent.SPECFEM_BUILD_PATH}/OUTPUT_FILES/output_solver.txt")
    if not success:
        print("8<--8<--8<--")
        print(output)
        print("8<--8<--8<--")