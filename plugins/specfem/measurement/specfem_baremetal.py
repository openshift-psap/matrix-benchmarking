import os, subprocess, math, socket

from . import specfemsimpleagent

NUM_WORKER_NODES = "<from configure>"
SPECFEM_BUILD_PATH = "<from configure>"
USE_SCALE_LAB = "<from configure>"
CONFIGURE_SH = "<from configure()>"

BUILD_AND_RUN_SH = "<from configure()>"
RUN_MESHER_SH = "<from configure()>"
RUN_SOLVER_SH = "<from configure()>"

SCALE_LAB_IPS = ["172.18.38.172", "172.18.37.12", "172.18.39.242", "172.18.36.125", "172.18.36.12", "172.18.37.96", "172.18.36.45", "172.18.38.11",
                 "172.18.39.243", "172.18.36.166", "172.18.36.99", "172.18.36.242", "172.18.39.108", "172.18.36.165", "172.18.37.88", "172.18.39.93",
                 "172.18.39.17", "172.18.39.100", "172.18.36.132", "172.18.38.149", "172.18.37.37", "172.18.38.211",  "172.18.36.15", "172.18.36.214",
                 "172.18.38.32", "172.18.37.196", "172.18.36.224", "172.18.38.111", "172.18.37.24",  "172.18.38.58", "172.18.36.73",  "172.18.39.25"]

def configure(plugin_cfg, machines):
    global SPECFEM_BUILD_PATH, NUM_WORKER_NODES, USE_SCALE_LAB, CONFIGURE_SH

    USE_SCALE_LAB = socket.gethostname() == plugin_cfg['scale_lab_frontend']
    print("USE_SCALE_LAB:", USE_SCALE_LAB)
    SPECFEM_BUILD_PATH = plugin_cfg['build_path']
    if USE_SCALE_LAB:
        NUM_WORKER_NODES = int(plugin_cfg['scale_lab']['num_bm_worker_nodes'])

    # must match plugin.specfem.scripts.install.sh
    CONFIGURE_SH = f"""
DATA_DIR="/data/kpouget"
BUILD_DIR="{SPECFEM_BUILD_PATH}"
SHARED_DIR="/mnt/cephfs/kevin"
SHARED_SPECFEM="$SHARED_DIR/specfem"
PODMAN_BASE_IMAGE="quay.io/kpouget/specfem"

export PATH="$PATH:/usr/lib64/openmpi/bin"
"""

    global BUILD_AND_RUN_SH, RUN_MESHER_SH, RUN_SOLVER_SH
    script_dir = os.path.dirname(__file__) + "/../scripts"
    with open(f"{script_dir}/build_and_run.sh") as f:
        BUILD_AND_RUN_SH = "".join(f.readlines())
    with open(f"{script_dir}/run_mesher.sh") as f:
        RUN_MESHER_SH = "".join(f.readlines())
    with open(f"{script_dir}/run_solver.sh") as f:
        RUN_SOLVER_SH = "".join(f.readlines())

# ssh -N -L localhost:1230:f12-h17-b01-5039ms.rdu2.scalelab.redhat.com:1230 root@f12-h17-b01-5039ms.rdu2.scalelab.redhat.com


def _prepare_system(env_cfg):
    with open(f"{SPECFEM_BUILD_PATH}/build_and_run.sh", "w") as script_f:
        print("#! /bin/bash", file=script_f)
        print("set -ex", file=script_f)
        print(CONFIGURE_SH, file=script_f)
        for env in env_cfg: print(env, file=script_f)
        print(BUILD_AND_RUN_SH, file=script_f)

    with open(f"{SPECFEM_BUILD_PATH}/run_mesher.sh", "w") as script_f:
        print("#! /bin/bash", file=script_f)
        print("set -e", file=script_f)
        print(CONFIGURE_SH, file=script_f)
        for env in env_cfg: print(env, file=script_f)
        print(RUN_MESHER_SH, file=script_f)

    with open(f"{SPECFEM_BUILD_PATH}/run_solver.sh", "w") as script_f:
        print("#! /bin/bash", file=script_f)
        print("set -e", file=script_f)
        print(CONFIGURE_SH, file=script_f)
        for env in env_cfg: print(env, file=script_f)
        print(RUN_SOLVER_SH, file=script_f)

def _prepare_mpi_hostfile(nproc, mpi_slots):
    hostfile = f"{SPECFEM_BUILD_PATH}/hostfile.mpi"
    with open(hostfile, "w") as hostfile_f:
        if USE_SCALE_LAB:
            for ip in SCALE_LAB_IPS:
                print(f"{ip} slots={mpi_slots}", file=hostfile_f)
        else:
            print(f"localhost slots=999", file=hostfile_f)
    return hostfile

def _specfem_set_par(key, new_val):
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

def _nvidia_mig_set_mode(_mode):
    mode = _mode.replace("-", ",")

    print(subprocess.check_output("nvidia-smi -mig 0 && nvidia-smi -mig 1", shell=True).decode('utf8'))
    print(subprocess.check_output(f"nvidia-smi mig -cgi '{mode}' -cgi 1", shell=True).decode('utf8'))
    print(subprocess.check_output("nvidia-smi mig -cci", shell=True).decode('utf8'))

def reset():
    hostfile = _prepare_mpi_hostfile("all", "1")
    cmd = ["mpirun",
           "--allow-run-as-root",
           "-hostfile", hostfile,
           "-np", str(len(SCALE_LAB_IPS)),
           "bash", "-c", "pkill xmeshfem3D; pkill xspecfem3D"
           ]
    print(" ".join(cmd))
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.wait()


def run_specfem(agent, driver, params):
    try: os.remove(f"{SPECFEM_BUILD_PATH}/OUTPUT_FILES/output_solver.txt")
    except FileNotFoundError: pass # ignore

    nex = specfemsimpleagent.get_param(params, "nex")
    _specfem_set_par("NEX_XI", nex)
    _specfem_set_par("NEX_ETA", nex)

    try:
        gpu = specfemsimpleagent.get_param(params, "gpu")
        _specfem_set_par("GPU_MODE", ".true.")
        _nvidia_mig_set_mode(gpu)

    except KeyError:
        _specfem_set_par("GPU_MODE", ".false.")

    mpi_nproc = int(specfemsimpleagent.get_param(params, "processes"))
    specfem_nproc = int(math.sqrt(mpi_nproc))
    _specfem_set_par("NPROC_XI", specfem_nproc)
    _specfem_set_par("NPROC_ETA", specfem_nproc)

    mpi_slots = int(specfemsimpleagent.get_param(params, "mpi-slots"))
    msg = f"INFO: running with mpi_nproc={mpi_nproc}, mpi_slots={mpi_slots}"
    print(msg)
    agent.feedback(msg)
    _prepare_mpi_hostfile(mpi_nproc, mpi_slots)

    num_threads = specfemsimpleagent.get_param(params, "threads")

    platform = specfemsimpleagent.get_param(params, "platform")
    use_podman = 1 if "podman" in platform  else 0

    use_shared_fs = specfemsimpleagent.get_param(params, "relyOnSharedFS").lower()

    env_cfg = [
        f"SPECFEM_USE_PODMAN={use_podman}",
        f"SPECFEM_MPI_NPROC={mpi_nproc}",
        f"MPI_SLOTS={mpi_slots}",
        f"OMP_NUM_THREADS={num_threads}",
        f"SPECFEM_USE_SHARED_FS={use_shared_fs}",
        f"SPECFEM_NEX={nex}",
        f"SPECFEM_PLATFORM='{platform}'"]

    try:
        oflag = specfemsimpleagent.get_param(params, "libgomp_optim")
        LIBGOMP_OPTIM_PATH = f"/data/kpouget/libgomp/libgomp/{oflag.upper()}/usr/lib64/"
        env_cfg.append(f"LD_LIBRARY_PATH={LIBGOMP_OPTIM_PATH}")
        if not os.path.exists(LIBGOMP_OPTIM_PATH):
            agent.feedback(f"Specfem finished without starting: libgomp optim lib not found ({LIBGOMP_OPTIM_PATH})")
            print(f"ERROR: libgomp optim directory doesn't exist ({LIBGOMP_OPTIM_PATH})")
            return
        msg = f"INFO: running with LIBGOMP flag '-{oflag.upper()}'"
        print(msg)
        agent.feedback(msg)
    except KeyError:
        msg = f"INFO: running with the system's libgomp"
        print(msg)
        agent.feedback(msg)

    _prepare_system(env_cfg)

    specfem_config = " | ".join(env_cfg)

    agent.feedback("config: "+specfem_config)
    cwd = SPECFEM_BUILD_PATH
    cmd = (["env"] + env_cfg + [f"SPECFEM_CONFIG={specfem_config}"] +  # for logging
           ["bash", "./build_and_run.sh"])

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

    specfemsimpleagent.parse_and_save_timing(agent, f"{SPECFEM_BUILD_PATH}/OUTPUT_FILES/output_solver.txt")
