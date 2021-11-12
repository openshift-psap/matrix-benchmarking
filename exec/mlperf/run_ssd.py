#! /usr/bin/python

import sys
import os
import subprocess
import time
import datetime
import json

from collections import defaultdict

import query_thanos

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
NODE_NAME = "dgxa100"

MIG_RES_TYPES = {
    "1g.5gb",
    "2g.10gb",
    "3g.20gb",
    "4g.20gb",
    "7g.40gb",
    "full"
}

def prepare_mig_gpu(mig_mode):
    if mig_mode == "full":
        migparted_res_type = "full"
        res_count = 1
        strategy = "none"
        k8s_res_type = "nvidia.com/gpu"

    else:
        try:
            migparted_res_type, _, res_count = mig_mode.rpartition("_")
            res_count = int(res_count)
            if not migparted_res_type in MIG_RES_TYPES: raise ValueError(f"{migparted_res_type} is invalid")
        except Exception as e:
            print(f"ERROR: failed to parse mig_mode='{mig_mode}'")
            print(e)
            return 1, ""
        strategy = "mixed"
        k8s_res_type = f"nvidia.com/mig-{migparted_res_type}"

    gpu_resources = f"""\
        # MIG mode: {mig_mode}
        limits:
          {k8s_res_type}: "{res_count}"
        requests:
          {k8s_res_type}: "{res_count}"
"""

    if migparted_res_type == "full": migparted_res_type = "disabled"
    mig_cmd = f"oc label --overwrite node/{NODE_NAME} nvidia.com/mig.config=all-{migparted_res_type}"

    print(mig_cmd)
    subprocess.check_call(mig_cmd, shell=True)

    return 0, gpu_resources

def save_thanos_metrics(thanos, thanos_start, thanos_stop):
    if not sys.stdout.isatty():
        with open("thanos.ts", "w") as out_f:
            print("start: {thanos_start}", file=out_f)
            print("stop: {thanos_stop}", file=out_f)

    for metrics in ["DCGM_FI_PROF_GR_ENGINE_ACTIVE", "DCGM_FI_PROF_DRAM_ACTIVE", "DCGM_FI_DEV_POWER_USAGE",
                    "cluster:cpu_usage_cores:sum",]:
        dest_fname = f"prom_{metrics}.json"
        try:
            print(f"Thanos: query {metrics} ({thanos_start} --> {thanos_stop})")
            if not (thanos_start and thanos_stop):
                print("... invalid thanos values, skipping.")
                continue
            thanos_values = query_thanos.query_values(thanos, metrics, thanos_start, thanos_stop)

            if not thanos_values:
                print("No metric values collected for {metrics}")
                with open(dest_fname, 'w'): pass
                continue

            if sys.stdout.isatty():
                print(f"Found {len(str(thanos_values))} chars for {os.getcwd()}/{dest_fname}")
            else:
                print(f"Saving {len(str(thanos_values))} chars for {os.getcwd()}/{dest_fname}")
                with open(dest_fname, 'w') as f:
                    json.dump(thanos_values, f)
        except Exception as e:
            print(f"WARNING: Failed to save {dest_fname} logs:")
            print(f"WARNING: {e.__class__.__name__}: {e}")

            with open(f'{dest_fname}failed', 'w') as f:
                print(f"{e.__class__.__name__}: {e}", file=f)
            pass

def main():
    print(datetime.datetime.now())

    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v

    mig_mode = settings["gpu"]
    ret, gpu_resources = prepare_mig_gpu(mig_mode)
    if ret: return ret

    if settings['benchmark'] == "ssd":
        POD_NAME = "run-ssd"
        POD_NAMESPACE = "default"
        CONFIG_CM_NAME = "custom-config-script"
        POD_TEMPLATE = "mlperf-ssd-pod.template.yaml"
        CM_FILES = [
            "my_run_and_time.sh",
        ]

    if settings['benchmark'] == "ssd":
        env_values = f"""
        - name: SSD_THRESHOLD
          value: "{settings['threshold']}"
        - name: DGXSOCKETCORES
          value: "{settings['cores']}"
"""

    privileged = settings.get('privileged', "false")

    with open(f"{THIS_DIR}/{POD_TEMPLATE}") as f:
        pod_template = f.read()

    pod_def = pod_template.format(
        pod_name=POD_NAME,
        pod_namespace=POD_NAMESPACE,
        privileged=privileged,
        env_values=env_values,
        gpu_resources=gpu_resources[:-1])
    print("=====")
    print(pod_def, end="")
    print("-----")

    sys.stdout.flush()
    sys.stderr.flush()

    subprocess.run(f"oc delete cm/{CONFIG_CM_NAME} -n {POD_NAMESPACE} 2>/dev/null", shell=True)

    cm_files = ""
    for cm_file in CM_FILES:
        cm_file_fullpath = f"{THIS_DIR}/{cm_file}"
        cm_files += f" --from-file={cm_file_fullpath}"
        print(f"Include {cm_file_fullpath}")

    subprocess.run(f"oc create configmap {CONFIG_CM_NAME} -n {POD_NAMESPACE} "+cm_files, shell=True)

    subprocess.run(f"oc delete pod/{POD_NAME} -n {POD_NAMESPACE} 2>/dev/null", shell=True)
    subprocess.run(f"oc create -f-", input=pod_def.encode('utf-8'),
                          shell=True, check=True)

    print("-----")
    print("Thanos: Preparing  ...")
    #thanos = query_thanos.prepare_thanos()
    thanos_start = None

    print("-----")
    print(f"Waiting for pod/{POD_NAME} to terminate successfully ...")
    cmd = f"oc get pod/{POD_NAME} -n {POD_NAMESPACE} \
               --no-headers \
               -o custom-columns=:status.phase"
    print(cmd)
    print(datetime.datetime.now())
    current_phase = None
    while True:
        try:
            phase = subprocess.check_output(cmd, shell=True).decode('ascii').strip()
        except subprocess.CalledProcessError:
            phase = "Runtime error"

        if phase != current_phase:
            current_phase = phase
            print(f"\n{current_phase}")

        #if thanos_start is None and phase == "Running":
        #    thanos_start = query_thanos.query_current_ts(thanos)
        #    print(f"Thanos: start time: {thanos_start}")
        if phase in ("Succeeded", "Error", "Failed"):
            break

        time.sleep(5)
        print(".", end="")
        sys.stdout.flush()

    print("-----")
    print(datetime.datetime.now())

    output = subprocess.check_output(f"oc logs pod/{POD_NAME} -n {POD_NAMESPACE} ", shell=True)

    #thanos_stop = query_thanos.query_current_ts(thanos)
    #print(f"Thanos: stop time: {thanos_start}")

    print("-----")
    print(output.decode('utf-8'), end="")
    print("-----")
    print("Directory:", os.getcwd())
    if not sys.stdout.isatty():
        print("Saving the logs in 'pod.logs' ...")
        with open("pod.logs", "w") as out_f:
            print(output.decode('utf-8'), file=out_f, end="")
    else:
        print("stdout is a TTY, not saving the logs into 'pod.logs'.")

    #print("-----")
    #save_thanos_metrics(thanos, thanos_start, thanos_stop)
    print("-----")

    print(datetime.datetime.now())

    if not "ALL FINISHED" in output.decode('utf-8'): return 1
    if "CUDNN_STATUS_INTERNAL_ERROR" in output.decode('utf-8'): return 1

    return 0

if __name__ == "__main__":
    exit(main())
