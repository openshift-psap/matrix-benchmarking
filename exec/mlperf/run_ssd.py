#! /usr/bin/python

import sys
import os
import subprocess
import time

from collections import defaultdict

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
MLPERF_SSD_POD_TEMPLATE = "mlperf-ssd.template.yaml"
MLPERF_SSD_CM_FILES = [
    "my_run_and_time.sh",
]

def main():
    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v

    mig_mode = settings["gpu"].replace("-", ",")
    mig_cmd = """echo oc patch clusterpolicy/cluster-policy --type merge --patch '{"spec": {"driver": {"migMode": "'""" + mig_mode + """'" }}}'"""
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

    privileged = settings.get('privileged', "false")
    with open(f"{THIS_DIR}/{MLPERF_SSD_POD_TEMPLATE}") as f:
        mlperf_ssd_pod_template = f.read()
    pod_def = mlperf_ssd_pod_template.format(
        pod_name=POD_NAME,
        pod_namespace=POD_NAMESPACE,
        privileged=privileged,
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
    print(f"Waiting for pod/{POD_NAME} to terminate successfully ...")
    cmd = f"oc get pod  --field-selector=status.phase=Succeeded,metadata.name={POD_NAME} --no-headers -oname -n {POD_NAMESPACE} | grep '{POD_NAME}' -q"
    print(cmd)
    while True:
        try:

            subprocess.check_call(cmd, shell=True)
            print("")
            break
        except subprocess.CalledProcessError: pass
        time.sleep(5)
        print(".", end="")
        sys.stdout.flush()
    print("-----")

    output = subprocess.check_output(f"oc logs pod/{POD_NAME} -n {POD_NAMESPACE} ", shell=True)
    #subprocess.run(f"oc delete pod/{POD_NAME} -n {POD_NAMESPACE} ", shell=True)
    print("-----")
    print(output.decode('utf-8'), end="")
    print("-----")
    if not sys.stdout.isatty():
        print("Saving the logs in 'pod.logs' ...")
        with open("pod.logs", "w") as out_f:
            print(output.decode('utf-8'), file=out_f, end="")
    else:
        print("stdout is a TTY, not saving the logs into 'pod.logs'.")
    print("=====")
    print("Done!")

    return 0

if __name__ == "__main__":
    exit(main())
