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

MIG_ID_TO_RES = {
    19: "nvidia.com/mig-1g.5gb",
    14: "nvidia.com/mig-2g.10gb",
    9: "nvidia.com/mig-3g.20gb",
    5: "nvidia.com/mig-4g.20gb",
    0: "nvidia.com/mig-7g.40gb",
    99: "nvidia.com/gpu",
}

POD_NAME = "run-ssd"
POD_NAMESPACE = "mlperf"
CONFIG_CM_NAME = "custom-config-script"
MLPERF_SSD_POD_TEMPLATE = "mlperf-ssd-pod.template.yaml"
MLPERF_SSD_CM_FILES = [
    "my_run_and_time.sh",
]

def main():
    print(datetime.datetime.now())

    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v

    mig_mode = settings["gpu"].replace("-", ",")

    strategy = "none" if mig_mode == "99" else "mixed"
    mig_cmd = """oc patch clusterpolicy/gpu-cluster-policy \
                    --type merge --patch \
                    '{"spec": {"gfd": {"migStrategy": "'""" + strategy + """'" }}}'"""
    if mig_mode != "99":
        mig_cmd += """;oc patch clusterpolicy/gpu-cluster-policy \
                          --type merge --patch \
                          '{"spec": {"driver": {"migMode": "'""" + mig_mode + """'" }}}'"""

    print(mig_cmd)
    subprocess.check_call(mig_cmd, shell=True)

    resources = defaultdict(int)
    try:
        mig_ids = list(map(int, mig_mode.split(",")))
    except Exception as e:
        print(f"ERROR: failed to parse mig_mode='{mig_mode}'")
        print(e)
        return 1
    for mig_id in mig_ids:
        resources[MIG_ID_TO_RES[mig_id]] += 1

    gpu_resources = ""
    for name, count in resources.items():
        gpu_resources += f'          {name}: "{count}"\n'

    gpu_resources = f"""\
        # MIG mode: {mig_mode}
        limits:
{gpu_resources}
        requests:
{gpu_resources}\
"""

    env_values = f"""
        - name: SSD_THRESHOLD
          value: "{settings['threshold']}"
        - name: DGXSOCKETCORES
          value: "{settings['cores']}"
"""

    privileged = settings.get('privileged', "false")
    with open(f"{THIS_DIR}/{MLPERF_SSD_POD_TEMPLATE}") as f:
        mlperf_ssd_pod_template = f.read()

    pod_def = mlperf_ssd_pod_template.format(
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
    for cm_file in MLPERF_SSD_CM_FILES:
        cm_file_fullpath = f"{THIS_DIR}/{cm_file}"
        cm_files += f" --from-file={cm_file_fullpath}"
        print(f"Include {cm_file_fullpath}")

    subprocess.run(f"oc create configmap {CONFIG_CM_NAME} -n {POD_NAMESPACE} "+cm_files, shell=True)

    subprocess.run(f"oc delete pod/{POD_NAME} -n {POD_NAMESPACE} 2>/dev/null", shell=True)
    subprocess.run(f"oc create -f-", input=pod_def.encode('utf-8'),
                          shell=True, check=True)

    print("-----")
    print("Thanos: Preparing  ...")
    thanos = query_thanos.prepare_thanos()
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
        phase = subprocess.check_output(cmd, shell=True).decode('ascii').strip()
        if phase != current_phase:
            current_phase = phase
            print(f"\n{current_phase}")

        if thanos_start is None and phase == "Running":
            thanos_start = query_thanos.query_current_ts(thanos)
            print(f"Thanos: start time: {thanos_start}")
        if phase in ("Succeeded", "Error", "Failed"):
            break

        time.sleep(5)
        print(".", end="")
        sys.stdout.flush()

    print("-----")
    print(datetime.datetime.now())

    output = subprocess.check_output(f"oc logs pod/{POD_NAME} -n {POD_NAMESPACE} ", shell=True)

    thanos_stop = query_thanos.query_current_ts(thanos)
    print(f"Thanos: stop time: {thanos_start}")

    print("-----")
    print(output.decode('utf-8'), end="")
    print("-----", os.getcwd())
    if not sys.stdout.isatty():
        print("Saving the logs in 'pod.logs' ...")
        with open("pod.logs", "w") as out_f:
            print(output.decode('utf-8'), file=out_f, end="")
    else:
        print("stdout is a TTY, not saving the logs into 'pod.logs'.")
    print("-----")
    for metrics in ["DCGM_FI_DEV_MEM_COPY_UTIL", "DCGM_FI_DEV_GPU_UTIL", "DCGM_FI_DEV_POWER_USAGE",
                    "cluster:cpu_usage_cores:sum",]:
        try:
            print("Thanos: query {metrics} ({thanos_start} --> {thanos_stop})")
            thanos_values = query_thanos.query_values(thanos, metrics, thanos_start, thanos_stop)

            if not thanos_values:
                print("No metric values collected for {metrics}")
                with open(f'{metrics}.json', 'w'): pass
                continue

            print(f"Saving {len(thanos_values['result'][0]['values'])} values for {metrics}")
            with open(f'{metrics}.json', 'w') as f:
                json.dump(thanos_values, f)
        except Exception as e:
            print(f"WARNING: Failed to save {metrics} logs:")
            print(f"WARNING: {e.__class__.__name__}: {e}")

            with open(f'{metrics}.json.failed', 'w') as f:
                print(f"{e.__class__.__name__}: {e}", file=f)
            pass

    print(datetime.datetime.now())

    return 0

if __name__ == "__main__":
    exit(main())
