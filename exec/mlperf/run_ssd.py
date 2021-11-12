#! /usr/bin/python

import sys
import os
import subprocess
import time
import datetime
import json
from pathlib import Path
from collections import defaultdict

import yaml

import kubernetes.client
import kubernetes.config
import kubernetes.utils

import query_thanos

from kubernetes.client import V1ConfigMap, V1ObjectMeta

kubernetes.config.load_kube_config()

v1 = kubernetes.client.CoreV1Api()
appsv1 = kubernetes.client.AppsV1Api()
batchv1 = kubernetes.client.BatchV1Api()
k8s_client = kubernetes.client.ApiClient()

THIS_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

if not sys.stdout.isatty():
    ARTIFACTS_DIR = Path(os.getcwd())
else:
    base_dir = Path("/tmp") / ("ci-artifacts_" + datetime.datetime.today().strftime("%Y%m%d"))
    base_dir.mkdir(exist_ok=True)
    current_length = len(list(base_dir.glob("*__*")))
    ARTIFACTS_DIR = base_dir / f"{current_length:03d}__benchmarking__run_ssd"
    ARTIFACTS_DIR.mkdir(exist_ok=True)

print(f"Saving artifacts files into {ARTIFACTS_DIR}")

NODE_NAME = "dgxa100"

MIG_RES_TYPES = {
    "1g.5gb",
    "2g.10gb",
    "3g.20gb",
    "4g.20gb",
    "7g.40gb",
    "full"
}

###

APP_NAME = "run-ssd"
NAMESPACE = "default"
CONFIG_CM_NAME = "custom-config-script"
JOB_TEMPLATE = "mlperf-ssd-job.template.yaml"
CM_FILES = [
    "my_run_and_time.sh",
]
ENABLE_THANOS = False

###
class objectview(object):
    def __init__(self, d):
        self.__dict__ = d

def parse_gpu_settings(settings):
    ret = objectview({})

    mig_mode = settings["gpu"]

    try:
        mig_res_type, res_count_str, parallelism_str, *extra = mig_mode.split("_")
        ret.res_count = int(res_count_str)
        ret.parallelism = int(parallelism_str)

        if not mig_res_type in MIG_RES_TYPES:
            raise ValueError(f"{ret.mig_res_type} is invalid")
    except Exception as e:
        print(f"ERROR: failed to parse mig_mode='{mig_mode}'")
        raise e

    if mig_res_type == "full":
        ret.k8s_res_type = "nvidia.com/gpu"
        ret.mig_label = "all-disabled"
    else:
        ret.k8s_res_type = f"nvidia.com/mig-{mig_res_type}"
        ret.mig_label = f"all-{mig_res_type}"

    return ret, extra


def save_thanos_metrics(thanos, thanos_start, thanos_stop):
    if not sys.stdout.isatty():
        with open(ARTIFACTS_DIR / "thanos.ts", "w") as out_f:
            print("start: {thanos_start}", file=out_f)
            print("stop: {thanos_stop}", file=out_f)

    for metrics in ["DCGM_FI_PROF_GR_ENGINE_ACTIVE", "DCGM_FI_PROF_DRAM_ACTIVE", "DCGM_FI_DEV_POWER_USAGE",
                    "cluster:cpu_usage_cores:sum",]:
        dest_fname = ARTIFACTS_DIR / f"prom_{metrics}.json"
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

            print(f"Saving {len(str(thanos_values))} chars for {os.getcwd()}/{dest_fname}")
            with open(dest_fname, 'w') as f:
                json.dump(thanos_values, f)
        except Exception as e:
            print(f"WARNING: Failed to save {dest_fname} logs:")
            print(f"WARNING: {e.__class__.__name__}: {e}")

            with open(f'{dest_fname}.failed', 'w') as f:
                print(f"{e.__class__.__name__}: {e}", file=f)
            pass

def prepare_configmap():
    print("Deleting the old ConfigMap, if any ...")
    try:
        v1.delete_namespaced_config_map(namespace=NAMESPACE, name=CONFIG_CM_NAME)
        print("Existed.")
    except kubernetes.client.exceptions.ApiException as e:
        if e.reason != "Not Found":
            raise e
        print("Didn't exist.")

    print("Creating the new ConfigMap ...")
    cm_data = {}
    for cm_file in CM_FILES:
        cm_file_fullpath = THIS_DIR / cm_file

        print(f"Including {cm_file} ...")
        with open(cm_file_fullpath) as f:
            cm_data[cm_file] = "".join(f.readlines())

    body = V1ConfigMap(
        metadata=V1ObjectMeta(
            name=CONFIG_CM_NAME,
        ), data=cm_data)

    v1.create_namespaced_config_map(namespace=NAMESPACE, body=body)


def cleanup_pod_jobs():
    print("Deleting the old Job, if any ...")
    jobs = batchv1.list_namespaced_job(namespace=NAMESPACE,
                                  label_selector=f"app={APP_NAME}")

    for job in jobs.items:
        try:
            print("-", job.metadata.name)
            batchv1.delete_namespaced_job(namespace=NAMESPACE, name=job.metadata.name)
        except kubernetes.client.exceptions.ApiException as e:
            if e.reason != "Not Found":
                raise e

    print("Deleting the old job Pods, if any ...")
    while True:
        pods = v1.list_namespaced_pod(namespace=NAMESPACE,
                                      label_selector=f"app={APP_NAME}")
        if not len(pods.items):
            break
        deleting_pods = []
        for pod in pods.items:
            try:
                print("-", pod.metadata.name)
                v1.delete_namespaced_pod(namespace=NAMESPACE, name=pod.metadata.name)
                deleting_pods.append(pod.metadata.name)
            except kubernetes.client.exceptions.ApiException as e:
                if e.reason != "Not Found":
                    raise e
        print(f"Deleting {len(deleting_pods)} Pods:", " ".join(deleting_pods))
        time.sleep(5)
    print("Done with the Pods.")

def create_job(settings, gpu_config, extra):
    print(f"Running {gpu_config.parallelism} Pods in parallel")
    print(f"Requesting {gpu_config.res_count} {gpu_config.k8s_res_type} per Pod")

    over_requesting = "y" if "over" in extra else "n"
    if over_requesting == "y":
        print("Over requesting mode enabled.")

    sync_identifier = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    with open(THIS_DIR / JOB_TEMPLATE) as f:
        job_template = f.read()

    job_spec = job_template.format(
        job_name=APP_NAME,
        namespace=NAMESPACE,

        k8s_res_type=gpu_config.k8s_res_type,
        res_count=gpu_config.res_count,

        parallelism=gpu_config.parallelism,
        over_requesting=over_requesting,

        sync_identifier=sync_identifier,

        settings_gpu=settings["gpu"],
        settings_cores=settings["cores"],
        settings_exec_mode=settings["execution_mode"],
        settings_threshold=settings["threshold"],

    )

    print("Creating the new Job ...")
    spec_file = ARTIFACTS_DIR / "job_spec.yaml"
    with open(spec_file, "w") as out_f:
        print(job_spec, file=out_f, end="")

    kubernetes.utils.create_from_yaml(k8s_client, spec_file)

def await_jobs():
    print("=====")

    if ENABLE_THANOS:
        print("Thanos: Preparing  ...")
        thanos = query_thanos.prepare_thanos()
        thanos_start = None

        print("-----")

    print(datetime.datetime.now())
    print(f"Waiting for {APP_NAME} to terminate ...")
    sys.stdout.flush()
    sys.stderr.flush()

    started = False
    current_phase = "..."

    pod_phases = defaultdict(str)
    ERASE_LINE = "\x1b[2K\r"

    while True:
        jobs = batchv1.list_namespaced_job(namespace=NAMESPACE,
                                  label_selector=f"app={APP_NAME}")
        all_finished = True
        for job in jobs.items:
            job = batchv1.read_namespaced_job(namespace=NAMESPACE, name=APP_NAME)
            active = job.status.active
            succeeded = job.status.succeeded
            failed = job.status.failed

            if not active: active = 0
            if not succeeded: succeeded = 0
            if not failed: failed = 0

            if sum([active, succeeded, failed]) == 0:
                phase = "Not started"
            else:
                phase = "Active" if active else "Finished"

            if phase != "Finished":
                all_finished = False

            if phase != current_phase:
                current_phase = phase
                print("\n"+f"{job.metadata.name} - {current_phase} (active={active}, succeeded={succeeded}, failed={failed})")

        pods = v1.list_namespaced_pod(namespace=NAMESPACE,
                                          label_selector=f"app={APP_NAME}")
        for pod in pods.items:
            phase = pod.status.phase

            if pod_phases[pod.metadata.name] != phase:
                print(ERASE_LINE+f"{pod.metadata.name} --> {phase}")
                pod_phases[pod.metadata.name] = phase

            if ENABLE_THANOS:
                if thanos_start is None and phase == "Running":
                    thanos_start = query_thanos.query_current_ts(thanos)
                    print(ERASE_LINE+f"Thanos: start time: {thanos_start}")


        if all_finished:
            break

        time.sleep(5)
        print(".", end="")
        sys.stdout.flush()

    print("-----")
    print(datetime.datetime.now())

def save_artifacts():
    failed = False

    pods = v1.list_namespaced_pod(namespace=NAMESPACE,
                                  label_selector=f"app={APP_NAME}")
    for pod in pods.items:
        phase = pod.status.phase

        print(f"{pod.metadata.name} --> {phase}")
        logs = v1.read_namespaced_pod_log(namespace=NAMESPACE, name=pod.metadata.name)
        dest_fname = ARTIFACTS_DIR /  f"{pod.metadata.name}.log"

        print(dest_fname)
        with open(dest_fname, "w") as log_f:
            print(logs, file=log_f, end="")

        if phase != "Succeeded": failed = True
        if not "ALL FINISHED" in logs: failed = True
        if "CUDNN_STATUS_INTERNAL_ERROR" in logs: failed = True

    if ENABLE_THANOS:
        thanos_stop = query_thanos.query_current_ts(thanos)
        print(f"Thanos: stop time: {thanos_start}")

        print("-----")
        save_thanos_metrics(thanos, thanos_start, thanos_stop)

    print("-----")
    print(datetime.datetime.now())
    print(f"Artifacts files saved into {ARTIFACTS_DIR}")

    if failed: return 1

    return 0

def apply_gpu_label(mig_label):
    print(f"Labeling node/{NODE_NAME} with MIG label '{mig_label}'")

    body = {
        "metadata": {
            "labels": {
                "nvidia.com/mig.config": mig_label}
        }
    }

    v1.patch_node(NODE_NAME, body)


def prepare_settings():
    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v
    return settings


def main():
    print(datetime.datetime.now())

    settings = prepare_settings()

    gpu_config, extra = parse_gpu_settings(settings)

    #

    apply_gpu_label(gpu_config.mig_label)

    prepare_configmap()

    cleanup_pod_jobs()

    create_job(settings, gpu_config, extra)

    await_job()

    return save_artifacts()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted ...")
