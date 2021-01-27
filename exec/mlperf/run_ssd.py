#! /usr/bin/python

import sys
import os
import subprocess
from collections import defaultdict

MIG_ID_TO_RES = {
    19: "nvidia.com/mig-1g.5gb",
    14: "nvidia.com/mig-2g.10gb",
    9: "nvidia.com/mig-3g.20gb",
    5: "nvidia.com/mig-4g.20gb",
    0: "nvidia.com/mig-7g.40gb",
}

MLPERF_SSH_POD_TEMPLATE = """
apiVersion: v1
kind: Pod
metadata:
  name: run-ssd
  namespace: mlperf
spec:
  containers:
  - image: "nvcr.io/nvidia/driver:450.80.02-rhcos4.6"
    name: nvidia
    command: # in the CLI debug command
    securityContext:
      privileged: {privileged}
    resources:
{gpu_resources}
"""
MLPERF_SSH_POD_COMMAND = "nvidia-smi -L"

def main():
    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v

    mig_mode = settings["gpu"].replace("-", ",")
    mig_cmd = """oc patch clusterpolicy/cluster-policy --type merge --patch '{"spec": {"driver": {"migMode": "'""" + mig_mode + """'" }}}'"""
    print(mig_cmd)
    subprocess.check_call(mig_cmd, shell=True)

    resources = defaultdict(int)
    for mig_id in map(int, mig_mode.split(",")):
        resources[MIG_ID_TO_RES[mig_id]] += 1

    gpu_resources = ""
    for name, count in resources.items():
        gpu_resources += f'        {name}: "{count}"\n'

    gpu_resources = f"""\
      # MIG mode: {mig_mode}
      limits:
{gpu_resources}
      requests:
{gpu_resources}\
"""

    privileged = settings.get('privileged', "false")
    pod_def = MLPERF_SSH_POD_TEMPLATE.format(
        privileged=privileged,
        gpu_resources=gpu_resources[:-1])
    print("=====")
    print(pod_def, end="")
    print("-----")
    sys.stdout.flush()
    sys.stderr.flush()
    output = subprocess.check_output(f"oc debug -f- -- {MLPERF_SSH_POD_COMMAND}",
                          shell=True, input=pod_def.encode('utf-8'))

    print("-----")
    print(output.decode('utf-8'))
    print("=====")
    print("Saving the logs in 'pod.logs' ...")
    with open("pod.logs", "w") as out_f:
        print(output.decode('utf-8'), file=out_f, end="")
    print("Done!")

    return 0

if __name__ == "__main__":
    exit(main())
