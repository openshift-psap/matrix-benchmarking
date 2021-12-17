#! /usr/bin/python3

import os, subprocess
import yaml

import specfem_config
import common

GO_CLIENT_CWD = "/home/kevin/openshift/specfem/specfem-client"
GO_CLIENT_CMD = ["go", "run", ".", "-config", "specfem-benchmark"]

NETWORK_MAPPING = {
    "multus": "Multus",
    "hostnet": "HostNetwork",
    "default": "Default"
}

DEFAULT_YAML = """\
apiVersion: specfem.kpouget.psap/v1alpha1
kind: SpecfemApp
metadata:
  name: specfem-sample
  namespace: specfem
spec:
  git:
    uri: https://gitlab.com/kpouget_psap/specfem3d_globe.git
    ref: master
  exec:
    nproc: 1
    ncore: 8
    slotsPerWorker: 1
  specfem:
    nex: 16
  resources:
    useUbiImage: true
    storageClassName: "ocs-external-storagecluster-cephfs"
    workerNodeSelector:
      node-role.kubernetes.io/worker:
    relyOnSharedFS: false
    networkType: default
    multus:
      mainNic: enp1s0f1
"""

def _specfem_set_yaml(path_key, value):
    if path_key is not None:
        with open(GO_CLIENT_CWD+"/config/specfem-benchmark.yaml", 'r') as f:
            yaml_cfg = yaml.safe_load(f)

        loc = yaml_cfg
        *path, key = path_key.split(".")
        for p in path: loc = loc[p]
        loc[key] = value
    else:
        yaml_cfg = yaml.safe_load(DEFAULT_YAML)

    with open(GO_CLIENT_CWD+"/config/specfem-benchmark.yaml", 'w') as f:
        yaml.dump(yaml_cfg, f)

def _specfem_get_yaml():
    with open(GO_CLIENT_CWD+"/config/specfem-benchmark.yaml", 'r') as f:
        yaml_cfg = yaml.safe_load(f)
        return yaml.dump(yaml_cfg)

def reset():
    cmd = GO_CLIENT_CMD + ["-delete", "mesher"]
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

def run_specfem():
    _specfem_set_yaml(None, None) # reset YAML file

    nex = int(specfemsimpleagent.get_param(params, "nex"))
    _specfem_set_yaml("spec.specfem.nex", int(nex))

    mpi_nproc = int(specfemsimpleagent.get_param(params, "processes"))
    _specfem_set_yaml("spec.exec.nproc", int(mpi_nproc))

    num_threads = specfemsimpleagent.get_param(params, "threads")
    _specfem_set_yaml("spec.exec.ncore", int(num_threads))

    mpi_slots = int(specfemsimpleagent.get_param(params, "mpi-slots"))
    _specfem_set_yaml("spec.exec.slotsPerWorker", int(mpi_slots))

    network = specfemsimpleagent.get_param(params, "network")
    _specfem_set_yaml("spec.resources.networkType", NETWORK_MAPPING[network])


    shared_fs = specfemsimpleagent.get_param(params, "relyOnSharedFS")
    _specfem_set_yaml("spec.resources.relyOnSharedFS", shared_fs)

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
        msg = f"ERROR: Specfem finished with errcode={errcode}"
        print(msg)
        agent.feedback(msg)
        return
    if log_filename is None:
        msg = f"ERROR: Specfem finished but the GO client failed to retrieve the solver logfile ..."
        print(msg)
        agent.feedback(msg)
        return
    print(f"INFO: Specfem finished successfully")
    specfemsimpleagent.parse_and_save_timing(agent,log_filename)

def main():
    print(datetime.datetime.now())

    settings = prepare_settings()

    set_artifacts_dir()

    run_specfem()

if __name__ == "__main__":
    sys.exit(main())
