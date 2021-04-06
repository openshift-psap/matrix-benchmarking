#! /usr/bin/python

import sys
import os
import subprocess
import time
import datetime

import run_ssd
import query_thanos

MLPERF_EXEC = "/home/kevin/openshift/matrix_benchmark/exec/mlperf"
GPU_BURN = "run_gpu_burn.sh"

def main():
    print(datetime.datetime.now())

    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v

    mig_mode = settings["gpu"]
    ret, gpu_resources, nvidia_visible_devices = run_ssd.prepare_mig_gpu(mig_mode)
    if ret != 0:
        return ret

    duration = int(settings["duration"])

    print("-----")
    print("Thanos: Preparing  ...")
    thanos = query_thanos.prepare_thanos()
    thanos_start = query_thanos.query_current_ts(thanos)
    print(f"Thanos: start time: {thanos_start}")

    print("-----")

    subprocess.run(["rm", "-f", "/tmp/gpu_burn.log"], check=True)

    ret = subprocess.run(["bash", f"{MLPERF_EXEC}/{GPU_BURN}", str(duration),
                          gpu_resources, nvidia_visible_devices]).returncode
    if ret != 0:
        print(f"GPU burn failed ... ({ret})")
        return ret

    thanos_stop = query_thanos.query_current_ts(thanos)

    print("-----")
    run_ssd.save_thanos_metrics(thanos, thanos_start, thanos_stop)
    print("-----")
    if sys.stdout.isatty():
        print("GPU burn logs:")
        subprocess.run("cat /tmp/gpu_burn.log", shell=True, check=True)
    else:
        print("Save GPU burn logs ...")
        subprocess.run("mv /tmp/gpu_burn.log .", shell=True, check=True)
    print("-----")

    print(datetime.datetime.now())

    return 0

if __name__ == "__main__":
    exit(main())
