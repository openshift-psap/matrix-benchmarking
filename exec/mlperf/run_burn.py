#! /usr/bin/python

import sys
import os
import subprocess
import time
import datetime

import run_ssd
import query_thanos

def main():
    print(datetime.datetime.now())

    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v

    mig_mode = settings["gpu"]
    ret = 0 #prepare_mig_gpu(mig_mode)
    if ret != 0:
        return ret

    CI_ARTIFACTS = "/home/kevin/openshift/ci-artifacts"
    GPU_BURN_TOOLBOX = "toolbox/gpu-operator/run_gpu_burn.sh"

    duration = int(settings["duration"])

    print("-----")
    print("Thanos: Preparing  ...")
    thanos = query_thanos.prepare_thanos()
    thanos_start = query_thanos.query_current_ts(thanos)
    print(f"Thanos: start time: {thanos_start}")

    print("-----")

    subprocess.run(["mkdir", "-p", "/tmp/benchmark"], check=True)
    ret = subprocess.run(["env", "ANSIBLE_OPTS=-e artifact_extra_logs_dir=/tmp/benchmark", f"{CI_ARTIFACTS}/{GPU_BURN_TOOLBOX}", str(duration)]).returncode
    if ret != 0:
        return ret
    thanos_stop = query_thanos.query_current_ts(thanos)

    print("-----")
    run_ssd.save_thanos_metrics(thanos, thanos_start, thanos_stop)
    print("-----")
    if sys.stdout.isatty():
        print("GPU burn logs:")
        subprocess.run("cat /tmp/benchmark/gpu_burn*", shell=True, check=True)
    else:
        print("Save GPU burn logs ...")
        subprocess.run("mv /tmp/benchmark/gpu_burn* .", shell=True, check=True)
    print("-----")

    print(datetime.datetime.now())

    return 0

if __name__ == "__main__":
    exit(main())
