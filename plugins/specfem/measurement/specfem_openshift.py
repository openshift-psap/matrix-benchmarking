import os, subprocess
import yaml

from . import specfemsimpleagent

GO_CLIENT_CWD = "/home/kevin/openshift/specfem/specfem-client"
GO_CLIENT_CMD = ["go", "run", ".", "-config", "specfem-benchmark"]

def _specfem_set_yaml(path_key, value):
    with open(GO_CLIENT_CWD+"/config/specfem-benchmark.yaml", 'r') as f:
        yaml_cfg = yaml.safe_load(f)

    loc = yaml_cfg
    *path, key = path_key.split(".")
    for p in path: loc = loc[p]
    loc[key] = value

    with open(GO_CLIENT_CWD+"/config/specfem-benchmark.yaml", 'w') as f:
        yaml.dump(yaml_cfg, f)
        
def _specfem_get_yaml():
    with open(GO_CLIENT_CWD+"/config/specfem-benchmark.yaml", 'r') as f:
        yaml_cfg = yaml.safe_load(f)
        return yaml.dump(yaml_cfg)

def reset():
    cmd = GO_CLIENT_CMD + ["-delete", "config"]
    process = subprocess.Popen(cmd, cwd=GO_CLIENT_CWD, stdout=subprocess.PIPE)
    process.wait()
    errcode = process.returncode
    if errcode != 0:
        output = process.communicate()[0].decode("utf-8")
        print("8<--8<--8<--")
        print(" ".join(cmd))
        print("8<--8<--8<--")
        print(output)
        print("8<--8<--8<--")
        
    return errcode

def run_specfem(agent, driver, params):
    nex = int(specfemsimpleagent.get_param(params, "nex"))
    _specfem_set_yaml("spec.specfem.nex", nex)

    mpi_nproc = int(specfemsimpleagent.get_param(params, "processes"))
    _specfem_set_yaml("spec.exec.nproc", mpi_nproc)
    
    num_threads = specfemsimpleagent.get_param(params, "threads")
    _specfem_set_yaml("spec.exec.ncore", mpi_nproc)

    nproc_per_worker = int(specfemsimpleagent.get_param(params, "nproc_per_worker"))
    _specfem_set_yaml("spec.exec.slotsPerWorker", nproc_per_worker)

    agent.feedback("config: "+_specfem_get_yaml())

    process = subprocess.Popen(GO_CLIENT_CMD, cwd=GO_CLIENT_CWD, stderr=subprocess.PIPE)

    log_filename = None
    while process.stderr.readable():
        line = process.stderr.readline().decode('utf8')

        if not line: break
        print("| "+line.rstrip())
        agent.feedback("| " + line)

        if "Saved solver logs into" in line:
            log_filename = line.split("'")[-2]
    process.wait()

    errcode = process.returncode
    
    if errcode != 0:
        print(f"ERROR: Specfem finished with errcode={errcode}")
        return
    if log_filename is None:
        print(f"ERROR: Specfem GO client failed to retrieve the solver logfile ...")
        return
    print(f"INFO: Specfem finished successfully")
    specfemsimpleagent.parse_and_save_timing(agent,log_filename)
