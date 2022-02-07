#! /usr/bin/python3

import os, subprocess, sys
import datetime
import yaml

from pathlib import Path


import specfem_config
import common

SPECFEM_GO_CLIENT_DIR = "SPECFEM_GO_CLIENT_DIR"
SPECFEM_GO_CLIENT_DEV_MODE = "SPECFEM_GO_CLIENT_DEV_MODE"
env = {
    SPECFEM_GO_CLIENT_DIR: None,
    SPECFEM_GO_CLIENT_DEV: "false",
}




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

def str2bool(v, strict=False):
  if v.lower() in ("yes", "true", "t", "1"): return True
  if not strict: return False
  if v.lower() in ("no", "false", "n", "0"): return False
  raise ValueError(f"Invalid boolean value: {v}")

def _specfem_set_yaml(path_key, value):
    if path_key is not None:
        with open(env[SPECFEM_GO_CLIENT_DIR] / "config" / "specfem-benchmark.yaml", 'r') as f:
            yaml_cfg = yaml.safe_load(f)

        loc = yaml_cfg
        *path, key = path_key.split(".")
        for p in path: loc = loc[p]
        loc[key] = value
    else:
        yaml_cfg = yaml.safe_load(DEFAULT_YAML)

    with open(env[SPECFEM_GO_CLIENT_DIR] / "config" / "specfem-benchmark.yaml", 'w') as f:
        yaml.dump(yaml_cfg, f)


def _specfem_get_yaml():
    with open(env[SPECFEM_GO_CLIENT_DIR] / "config" / "specfem-benchmark.yaml", 'r') as f:
        yaml_cfg = yaml.safe_load(f)
        return yaml.dump(yaml_cfg)


def reset(): # not used at the moment
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


def run_specfem(settings):
    _specfem_set_yaml(None, None) # reset the YAML file

    _specfem_set_yaml("spec.specfem.nex", int(settings["nex"]))
    _specfem_set_yaml("spec.exec.nproc", int(settings["processes"]))
    _specfem_set_yaml("spec.exec.ncore", int(settings["threads"]))
    _specfem_set_yaml("spec.exec.slotsPerWorker", int(settings["mpi-slots"]))
    _specfem_set_yaml("spec.resources.networkType", NETWORK_MAPPING[settings["network"]])
    _specfem_set_yaml("spec.resources.relyOnSharedFS", settings["relyOnSharedFS"])

    print(_specfem_get_yaml())


    specfem_cmd = ["go", "run", "."] if env[SPECFEM_GO_CLIENT_DEV_MODE] else "./specfem-client"

    specfem_cmd += ["-config", "specfem-benchmark"]

    print(f"cd {env[SPECFEM_GO_CLIENT_DIR]}; {' '.join(specfem_cmd)}")
    process = subprocess.Popen(specfem_cmd, cwd=env[SPECFEM_GO_CLIENT_DIR], stderr=subprocess.PIPE)

    log_filename = None
    while process.stderr.readable():
        line = process.stderr.readline().decode('utf8')

        if not line: break
        print("| "+line.rstrip())

        if "Saved solver logs into" in line:
            log_filename = line.split("'")[-2]

    process.wait()

    errcode = process.returncode

    if errcode != 0:
        print(f"ERROR: Specfem finished with errcode={errcode}")

    elif log_filename is None:
        print(f"ERROR: Specfem finished but the GO client failed to retrieve the solver logfile ...")

    else:
        print(f"INFO: Specfem finished successfully")


def prepare_settings():
    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v

    for env_key in env:
        try:
            env[env_key] = settings.pop(env_key)

        except KeyError as e:
            from_settings = os.getenv(env_key)

            if from_settings is not None:
                env[env_key] = from_settings

            elif env[env_key] is not None:
                pass # using hardcoded default value
            else:
                raise e

        print(f"INFO: {env_key}={env[env_key]}")

    env[SPECFEM_GO_CLIENT_DIR] = Path(env[SPECFEM_GO_CLIENT_DIR])

    env[SPECFEM_GO_CLIENT_DEV_MODE] = str2bool(env[SPECFEM_GO_CLIENT_DEV_MODE], strict=True)

    return settings


def set_artifacts_dir():
    global ARTIFACTS_DIR

    if sys.stdout.isatty():
        base_dir = Path("/tmp") / ("ci-artifacts_" + datetime.datetime.today().strftime("%Y%m%d"))
        base_dir.mkdir(exist_ok=True)
        current_length = len(list(base_dir.glob("*__*")))
        ARTIFACTS_DIR = base_dir / f"{current_length:03d}__benchmarking__run_specfem"
        ARTIFACTS_DIR.mkdir(exist_ok=True)
    else:
        ARTIFACTS_DIR = Path(os.getcwd())

    print(f"Saving artifacts files into {ARTIFACTS_DIR}")

    global ARTIFACTS_SRC
    ARTIFACTS_SRC = ARTIFACTS_DIR / "src"
    ARTIFACTS_SRC.mkdir(exist_ok=True)


def main():
    print(datetime.datetime.now())

    settings = prepare_settings()

    set_artifacts_dir()

    run_specfem(settings)

if __name__ == "__main__":
    sys.exit(main())
