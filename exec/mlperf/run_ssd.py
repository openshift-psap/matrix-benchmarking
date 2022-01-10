#! /usr/bin/python -u

import sys
import os
import subprocess
import time
import datetime
import json
from pathlib import Path
from collections import defaultdict

import yaml

import query_thanos

import kubernetes.client
import kubernetes.config
import kubernetes.utils

from kubernetes.client import V1ConfigMap, V1ObjectMeta

kubernetes.config.load_kube_config()

v1 = kubernetes.client.CoreV1Api()
appsv1 = kubernetes.client.AppsV1Api()
batchv1 = kubernetes.client.BatchV1Api()
customv1 = kubernetes.client.CustomObjectsApi()

k8s_client = kubernetes.client.ApiClient()

THIS_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS_DIR = None # set in set_artifacts_dir
ARTIFACTS_SRC = None # set in set_artifacts_dir

NODE_NAME = None

MIG_RES_TYPES = {
    "1g.5gb",
    "2g.10gb",
    "3g.20gb",
    "4g.20gb",
    "7g.40gb",
    "full"
}

###

MAX_START_TIME = 5 # minutes before failing the test if some pods are still pending
MAX_RECONFIGURE_TIME = 5 # minutes before failing the test if the MIG reconfiguration didn't complete

ENABLE_THANOS = True
thanos = None
thanos_start = None

benchmark = None

APP_NAME = "run-mlperf"
NAMESPACE = "default"
CONFIG_CM_NAME = "custom-config-script"
JOB_TEMPLATE = "mlperf.job-template.yaml"
CM_FILES = [
    "my_run_and_time.sh",
]

BENCHMARK_IMAGE = {
    "ssd": "ssd_0.7",
    "maskrcnn": "maskrcnn_1.1_dell",
}
BENCHMARK_WORKDIR = {
    "ssd": "/workspace/single_stage_detector",
    "maskrcnn": "/workspace/object_detection",
}
###

class objectview(object):
    def __init__(self, d):
        self.__dict__ = d

def set_artifacts_dir():
    global ARTIFACTS_DIR

    if sys.stdout.isatty():
        base_dir = Path("/tmp") / ("ci-artifacts_" + datetime.datetime.today().strftime("%Y%m%d"))
        base_dir.mkdir(exist_ok=True)
        current_length = len(list(base_dir.glob("*__*")))
        ARTIFACTS_DIR = base_dir / f"{current_length:03d}__benchmarking__run_{benchmark}"
        ARTIFACTS_DIR.mkdir(exist_ok=True)
    else:
        ARTIFACTS_DIR = Path(os.getcwd())

    print(f"Saving artifacts files into {ARTIFACTS_DIR}")

    global ARTIFACTS_SRC
    ARTIFACTS_SRC = ARTIFACTS_DIR / "src"
    ARTIFACTS_SRC.mkdir(exist_ok=True)

    with open(ARTIFACTS_SRC / "namespace", "w") as out_f:
        print(NAMESPACE, file=out_f)

    with open(ARTIFACTS_SRC / "app_name", "w") as out_f:
        print(APP_NAME, file=out_f)

def prepare_settings():
    global NODE_NAME

    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v

    NODE_NAME = settings.get("node_name")
    if not NODE_NAME:
        print("FATAL: 'node_name' not provided in the settings")
        sys.exit(1)

    global benchmark
    benchmark = settings.get("benchmark")
    if not benchmark:
        print("FATAL: the benchmark name must be provided in the settings")
        sys.exit(1)

    if benchmark not in ("ssd", "maskrcnn"):
        print(f"FATAL: the benchmark name must be 'ssd' or 'maskrcnn', not '{benchmark}'")
        sys.exit(1)

    return settings


def parse_gpu_settings(settings):
    ret = objectview({})

    mig_mode = settings["gpu_type"]

    ret.res_count = settings["gpu_count"]
    ret.parallelism = settings["pod_count"]

    opts = []
    if "opts" in settings:
        opts = settings["opts"].split(",")

    ret.k8s_res_types = []
    if mig_mode not in MIG_RES_TYPES:
        if "," not in mig_mode:
            print(f"ERROR: failed to parse gpu_type='{mig_mode}'")
            raise ValueError(f"{mig_mode} is invalid")
        else:
            for mode in mig_mode.split(","):
                if mode not in MIG_RES_TYPES:
                    print(f"ERROR: failed to parse gpu_type=['{mode}']")
                    raise ValueError(f"{mode} is invalid")
                ret.k8s_res_types.append(f"nvidia.com/mig-{mode}")

    ret.mig_strategy = settings.get("mig_strategy", "mixed")
    if ret.mig_strategy not in ("single", "mixed"):
        raise ValueError("mig_strategy must be empty, mixed or single. Default is mixed.")

    if ret.mig_strategy == "single":
        ret.mig_label = f"all-{mig_mode}"

        if ret.k8s_res_types:
            raise ValueError("Cannot have multiple GPU types with 'single' strategy...")
        ret.k8s_res_types.append("nvidia.com/gpu")

    elif ret.k8s_res_types:
        try:
            ret.mig_label = settings["mig_label"]
        except KeyError as e:
            print("ERROR: 'mig_label' setting must be set when providing multiple 'gpu_type'")
            raise e
    elif mig_mode == "full":
        ret.k8s_res_types.append("nvidia.com/gpu")
        ret.mig_label = "all-disabled"
    else:
        ret.k8s_res_types.append(f"nvidia.com/mig-{mig_mode}")
        ret.mig_label = f"all-{mig_mode}"

    try: ret.mig_label = settings["mig_label"]
    except KeyError: pass # ignore, MIG label not forced

    return ret, opts

metrics = None
def get_metrics_list():
    global metrics
    if metrics is not None:
        return metrics

    metrics = {}
    with open(THIS_DIR / "metrics.list") as in_f:
        for line in in_f.readlines():
            if not line.startswith("# HELP "): continue
            # eg: '# HELP DCGM_FI_DEV_FB_USED Framebuffer memory used (in MiB).'
            _, _, metric, descr = line.strip().split(maxsplit=3)
            metrics[metric] = descr
    return metrics

def save_thanos_metrics(thanos, thanos_start, thanos_stop):
    if not sys.stdout.isatty():
        with open(ARTIFACTS_DIR / "thanos.yaml", "w") as out_f:
            print(f"start: {thanos_start}", file=out_f)
            print(f"stop: {thanos_stop}", file=out_f)
    metrics_dir = ARTIFACTS_DIR / "metrics"
    metrics_dir.mkdir(exist_ok=True)

    for metric, descr in get_metrics_list().items():
        dest_fname = metrics_dir / f"prom_{metric}.json"
        try:
            if not (thanos_start and thanos_stop):
                print("... invalid thanos values, skipping.")
                continue
            thanos_values = query_thanos.query_values(thanos, metric, thanos_start, thanos_stop)

            if not thanos_values:
                print("No metric values collected for {metric}")
                with open(dest_fname, 'w'): pass
                continue

            thanos_values["__metric_name"] = metric
            thanos_values["__metric_descr"] = descr

            print(f"Saving {metric} metrics ...")
            with open(dest_fname, 'w') as out_f:
                json.dump(thanos_values, out_f)

        except Exception as e:
            print(f"WARNING: Failed to save {dest_fname} logs:")
            print(f"WARNING: {e.__class__.__name__}: {e}")

            with open(f'{dest_fname}.failed', 'w') as out_f:
                print(f"{e.__class__.__name__}: {e}", file=out_f)
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
        with open(cm_file_fullpath) as in_f:
            cm_data[cm_file] = "".join(in_f.readlines())

    body = V1ConfigMap(
        metadata=V1ObjectMeta(
            name=CONFIG_CM_NAME,
        ), data=cm_data)

    v1.create_namespaced_config_map(namespace=NAMESPACE, body=body)

    print(f"Saving the ConfigMap in {ARTIFACTS_DIR} ...")
    cm = v1.read_namespaced_config_map(namespace=NAMESPACE, name=body.metadata.name)

    cm_dict = cm.to_dict()

    try: del cm_dict["metadata"]["managed_fields"]
    except KeyError: pass # ignore

    dest_fname = ARTIFACTS_SRC / "entrypoint.cm.yaml"
    with open(dest_fname, "w") as out_f:
        yaml.dump(cm_dict, out_f)

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
                v1.delete_namespaced_pod(namespace=NAMESPACE, name=pod.metadata.name)
                deleting_pods.append(pod.metadata.name)
            except kubernetes.client.exceptions.ApiException as e:
                if e.reason != "Not Found":
                    raise e
        print(f"Deleting {len(deleting_pods)} Pods:", " ".join(deleting_pods))
        time.sleep(5)
    print("Done with the Pods.")

SYNC_IDENTIFIER = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
def create_job(k8s_res_type, settings, gpu_config, opts):
    print(f"Running {gpu_config.parallelism} Pods in parallel")
    print(f"Requesting {gpu_config.res_count} {k8s_res_type} per Pod")

    no_sync = "y" if "no-sync" in opts else "n"
    if no_sync == "y":
        print("Pod synchronous start disabled (no-sync)")

    with open(THIS_DIR / JOB_TEMPLATE) as in_f:
        job_template = in_f.read()

    run_descr = f"GPU: {settings['gpu_count']} x {settings['gpu_type']} x {settings['pod_count']} Pods"

    job_name = APP_NAME
    if len(gpu_config.k8s_res_types) > 1:
        job_name += "-"+k8s_res_type.replace(".", "-").rpartition("/")[-1]

    sync_counter = int(gpu_config.parallelism) * len(gpu_config.k8s_res_types)

    job_spec = job_template.format(
        job_name=job_name,
        app_name=APP_NAME,
        namespace=NAMESPACE,

        k8s_res_type=k8s_res_type,
        res_count=gpu_config.res_count,
        parallelism=gpu_config.parallelism,

        sync_identifier=SYNC_IDENTIFIER,
        sync_counter=sync_counter,
        no_sync=no_sync,

        benchmark_image_tag=BENCHMARK_IMAGE[benchmark],
        workdir=BENCHMARK_WORKDIR[benchmark],

        settings_run_descr=run_descr,
        settings_benchmark=benchmark,
        settings_cores=settings["cores"],
        settings_exec_mode=settings["execution_mode"],
        settings_gpu_type=settings["gpu_type"],
        settings_threshold=settings.get("threshold"),
    )

    print(f"Creating the new '{k8s_res_type}' Job ...")
    spec_file = ARTIFACTS_SRC / f"job_spec.{job_name}.yaml"
    with open(spec_file, "w") as out_f:
        print(job_spec, end="", file=out_f)

    kubernetes.utils.create_from_yaml(k8s_client, spec_file)

    print()
    print(f"Job '{k8s_res_type}' for {run_descr} created!")

def await_completion(opts):
    print("=====")

    no_sync = "no-sync" in opts

    if ENABLE_THANOS:
        print("Thanos: Preparing  ...")
        global thanos, thanos_start
        thanos = query_thanos.prepare_thanos()
        thanos_start = None

        print("-----")

    print(datetime.datetime.now())
    print(f"Waiting for {APP_NAME} to complete its execution ...")
    sys.stdout.flush()
    sys.stderr.flush()

    started = False

    pod_phases = defaultdict(str)
    job_states = defaultdict(str)

    ERASE_LINE = "\x1b[2K\r"

    wait_start = datetime.datetime.now()
    exec_start = None
    printed_time = None

    failure_detected = False

    while True:
        jobs = batchv1.list_namespaced_job(namespace=NAMESPACE,
                                  label_selector=f"app={APP_NAME}")

        all_finished = True
        for job in jobs.items:
            job = batchv1.read_namespaced_job(namespace=NAMESPACE, name=job.metadata.name)
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

            job_state = f"{job.metadata.name} - {phase} (active={active}, succeeded={succeeded}, failed={failed})"
            if job_state != job_states[job.metadata.name]:
                job_states[job.metadata.name] = job_state
                print("\n"+job_state)

            if failed:
                print(f"ERROR: Failure detected in Job {job.metadata.name}, aborting...")
                failure_detected = True
                all_finished = True
                break

        if all_finished:
            break

        pods = v1.list_namespaced_pod(namespace=NAMESPACE,
                                          label_selector=f"app={APP_NAME}")
        for pod in pods.items:
            phase = pod.status.phase

            if phase == "Running":
                if no_sync and exec_start is None:
                    print("Execution started!")
                    exec_start = datetime.datetime.now()
                    printed_time = None
                    wait_start = None

                if ENABLE_THANOS and thanos_start is None:
                    thanos_start = query_thanos.query_current_ts(thanos)
                    print(ERASE_LINE+f"Thanos: start time: {thanos_start}")

            if pod_phases[pod.metadata.name] != phase:
                print(ERASE_LINE+f"{pod.metadata.name} --> {phase}")
                pod_phases[pod.metadata.name] = phase

            if phase == "Failed":
                print(f"ERROR: Failure detected in Pod {pod.metadata.name}, aborting...")
                all_finished = True
                failure_detected = True
                break

        if not no_sync and exec_start is None:
            if "Pending" not in pod_phases.values():
                print("Execution started!")
                exec_start = datetime.datetime.now()
                printed_time = None
                wait_start = None

        if wait_start:
            wait_time = (datetime.datetime.now() - wait_start).seconds / 60
            if wait_time >= MAX_START_TIME:
                print(ERASE_LINE+f"ERROR: Pods execution didn't properly start after {wait_time:.1f} minutes, aborting...")
                all_finished = True
                failure_detected = True
                break

            if no_sync:
                # Pods may stay pending until the previous one is finished
                if "Running" in pod_phases.values():
                    wait_start = None
            else:
                # all synced
                if "Pending" not in pod_phases.values():
                    wait_start = None

        else:
            if no_sync:
                if "Running" not in pod_phases.values():
                    if "Pending" in pod_phases.values():
                        print("Restart waiting for Pod execution ...")
                        wait_start = datetime.datetime.now()
                    else:
                        if "Failed" in pod_phases.values():
                            failure_detected = True
                            all_finished = True
            else:
                if "Running" not in pod_phases.values():
                    all_finished = True

        if all_finished:
            break

        time.sleep(5)
        if exec_start:
            print(".", end="")
            run_time = round((datetime.datetime.now() - exec_start).seconds / 60)
            if not (run_time % 5) and run_time and run_time != printed_time:
                print(ERASE_LINE + f"{run_time} minutes of execution ...")
                printed_time = run_time
        else:
            print("x", end="")
            wait_time = round((datetime.datetime.now() - wait_start).seconds / 60)
            if not (wait_time % 1) and wait_time and wait_time != printed_time:
                print(ERASE_LINE + f"{wait_time} minutes of wait ...")
                printed_time = wait_time

        sys.stdout.flush()

    print("-----")
    print(datetime.datetime.now())

    return not failure_detected

def save_artifacts(is_successful):
    print("-----")
    print("Collecting artifacts ...")

    def save_node():
        print(f"Saving {NODE_NAME} definition ...")
        node = v1.read_node(NODE_NAME)
        node_dict = node.to_dict()


        try: del node_dict["metadata"]["managed_fields"]
        except KeyError: pass # ignore

        try: del node_dict["status"]["images"]
        except KeyError: pass # ignore

        dest_fname = ARTIFACTS_DIR / f"node_{NODE_NAME}.yaml"
        with open(dest_fname, "w") as out_f:
            yaml.dump(node_dict, out_f)


    def save_version():
        print("Saving OpenShift version ...")

        version_dict = customv1.get_cluster_custom_object("config.openshift.io", "v1",
                                                     "clusterversions", "version")
        try: del version_dict["metadata"]["managedFields"]
        except KeyError: pass # ignore

        dest_fname = ARTIFACTS_DIR / "ocp_version.yaml"
        with open(dest_fname, "w") as out_f:
            yaml.dump(version_dict, out_f)


    def save_jobs():
        print(f"Saving {APP_NAME} Jobs ...")

        jobs = batchv1.list_namespaced_job(namespace=NAMESPACE,
                                           label_selector=f"app={APP_NAME}")

        dest_fname = ARTIFACTS_DIR / "jobs_status.yaml"
        with open(dest_fname, "w") as out_f:
            for job in jobs.items:
                job_dict = job.to_dict()

                try: del job_dict["metadata"]["managedFields"]
                except KeyError: pass # ignore

                if len(jobs.items) > 1:
                    print("---", file=out_f)
                yaml.dump(job_dict, out_f)

    def save_clusterpolicy():
        print("Saving the ClusterPolicy ...")

        cluster_policy_dict = customv1.get_cluster_custom_object("nvidia.com", "v1",
                                                                 "clusterpolicies", "gpu-cluster-policy")

        dest_fname = ARTIFACTS_DIR / "clusterpolicy.yaml"
        with open(dest_fname, "w") as out_f:
            yaml.dump(cluster_policy_dict, out_f)


    def save_gpu_operator_deployment():
        print("Saving the ClusterPolicy ...")

        operator_deploy = appsv1.read_namespaced_deployment(name="gpu-operator", namespace="nvidia-gpu-operator")
        operator_deploy_dict = operator_deploy.to_dict()

        try: del operator_deploy_dict["metadata"]["managed_fields"]
        except KeyError: pass # ignore

        dest_fname = ARTIFACTS_DIR / "deployment_gpu_operator.yaml"
        with open(dest_fname, "w") as out_f:
            yaml.dump(operator_deploy_dict, out_f)

    def save_image_sha():
        print("Saving the image SHA")
        pods = v1.list_namespaced_pod(namespace=NAMESPACE,
                                      label_selector=f"app={APP_NAME}")
        dest_fname = ARTIFACTS_DIR / "pod_image.yaml"
        with open(dest_fname, "w") as out_f:
            for pod in pods.items:
                try:
                    container_status = pod.status.container_statuses[0]
                except Exception:
                    print(f"Could not get the container status of pod/{pod.metadata.name}")
                    continue
                print(f"Found container status in pod/{pod.metadata.name}:")
                print(f"- {container_status.image}")
                print(f"- {container_status.image_id}")

                print(f"image: {container_status.image}", file=out_f)
                print(f"image_id: {container_status.image_id}", file=out_f)
                break


    save_node()
    save_version()
    save_jobs()
    save_image_sha()

    if ENABLE_THANOS and is_successful:
        if thanos_start:
            thanos_stop = query_thanos.query_current_ts(thanos)
            print(f"Thanos: stop time: {thanos_stop}")

            save_thanos_metrics(thanos, thanos_start, thanos_stop)

        else:
            print("Thanos start time not captured, not recording metrics.")
        print("-----")

    failed = not is_successful

    pods = v1.list_namespaced_pod(namespace=NAMESPACE,
                                  label_selector=f"app={APP_NAME}")
    for pod in pods.items:
        phase = pod.status.phase

        print(f"{pod.metadata.name} --> {phase}")
        logs = v1.read_namespaced_pod_log(namespace=NAMESPACE, name=pod.metadata.name)
        dest_fname = ARTIFACTS_DIR /  f"{pod.metadata.name}.log"

        print(dest_fname)
        with open(dest_fname, "w") as out_f:
            print(logs, end="", file=out_f)

        if phase != "Succeeded":
            failed = True

        if phase == "Running":
            job_name = pod.metadata.labels["job-name"]
            print(f"Killing Job {job_name} ...")
            try:
                batchv1.delete_namespaced_job(namespace=NAMESPACE, name=job_name)
            except kubernetes.client.exceptions.ApiException as e:
                if e.reason != "Not Found": raise e

            print(f"Killing Pod {pod.metadata.name} still running ...")
            v1.delete_namespaced_pod(namespace=NAMESPACE, name=pod.metadata.name)

        if not "ALL FINISHED" in logs: failed = True
        if "CUDNN_STATUS_INTERNAL_ERROR" in logs: failed = True

    print("-----")
    print(datetime.datetime.now())
    print(f"Artifacts files saved into {ARTIFACTS_DIR}")

    return 1 if failed else 0

def apply_gpu_label(mig_label):
    print(f"Labeling node/{NODE_NAME} with MIG label '{mig_label}'")

    body = {
        "metadata": {
            "labels": {
                "nvidia.com/mig.config": mig_label}
        }
    }

    v1.patch_node(NODE_NAME, body)

def apply_gpu_strategy(mig_strategy):
    print(f"Apply {mig_strategy} MIG strategy ...")

    dest_fname = ARTIFACTS_DIR / "src" / "mig-strategy.txt"
    with open(dest_fname, "w") as out_f:
        print(f"ClusterPolicy.spec.mig.strategy={mig_strategy}", file=out_f)

    body = {
        "spec": {
            "mig": {
                "strategy": mig_strategy}
        }
    }

    customv1.patch_cluster_custom_object("nvidia.com", "v1",
                                         "clusterpolicies", "gpu-cluster-policy",
                                         body)

def apply_gpu_label(mig_label):
    dest_fname = ARTIFACTS_DIR / "src" / "mig-label.txt"
    with open(dest_fname, "w") as out_f:
        print(f"node/{NODE_NAME}: metadata.labels: nvidia.com/mig.config: {mig_label}", file=out_f)


    node = v1.read_node(NODE_NAME)
    if node.metadata.labels.get("nvidia.com/mig.config") == mig_label:
        print(f"Node {NODE_NAME} already labeled with MIG label '{mig_label}', nothing to do.")
        return

    print(f"Labeling node/{NODE_NAME} with MIG label '{mig_label}' ...")
    body = {
        "metadata": {
            "labels": {
                "nvidia.com/mig.config": mig_label,
                "nvidia.com/mig.config.state": "pending-update"
            }
        }
    }

    v1.patch_node(NODE_NAME, body)

def wait_for_mig_reconfiguration(gpu_config):
    print("Waiting for MIG reconfiguration of the node ...")
    wait_start = None
    while True:
        if wait_start is None:
            wait_start = datetime.datetime.now()
        else:
            time.sleep(5)

        wait_time = (datetime.datetime.now() - wait_start).seconds / 60
        if wait_time >= MAX_RECONFIGURE_TIME:
            raise RuntimeError("MIG reconfiguration took too long ...")

        sys.stdout.flush()
        sys.stderr.flush()

        node = v1.read_node(NODE_NAME)

        mig_manager_state = node.metadata.labels.get("nvidia.com/mig.config.state")
        if mig_manager_state == "pending":
            print("MIG Manager state:", mig_manager_state)
            continue

        if mig_manager_state == "failed":
            raise RuntimeError("MIG reconfiguration failed ...")

        print(f"MIG Manager state is {mig_manager_state}, good.")
        if gpu_config.mig_label != "all-disabled":
            mig_strategy = node.metadata.labels.get("nvidia.com/mig.strategy")
            if mig_strategy != gpu_config.mig_strategy:
                print(f"MIG strategy is wrong: {mig_strategy} ...")
                continue
            print(f"MIG strategy is {mig_strategy}, good.")

        mig_config = node.metadata.labels.get("nvidia.com/mig.config")
        if mig_config != gpu_config.mig_label:
            print(f"MIG label is wrong ...")
            continue
        print(f"MIG label is {mig_config}, good.")

        all_good = True
        for k8s_res_type in gpu_config.k8s_res_types:
            try:
                if node.status.capacity[k8s_res_type] == "0":
                    print(f"No {k8s_res_type} resources...")
                    all_good = False
                else:
                    print(f"{node.status.capacity[k8s_res_type]} {k8s_res_type}, good.")
            except KeyError:
                # missing
                print(f"Resource {k8s_res_type} not known...")
                all_good = False

        if not all_good:
            continue

        break

def main():
    print(datetime.datetime.now())

    settings = prepare_settings()

    set_artifacts_dir()

    gpu_config, opts = parse_gpu_settings(settings)

    # --- #

    cleanup_pod_jobs()

    apply_gpu_strategy(gpu_config.mig_strategy)
    apply_gpu_label(gpu_config.mig_label)

    prepare_configmap()

    wait_for_mig_reconfiguration(gpu_config)

    print(f"Launching {gpu_config.parallelism * len(gpu_config.k8s_res_types)} Pods ...")
    for k8s_res_type in gpu_config.k8s_res_types:
        create_job(k8s_res_type, settings, gpu_config, opts)

    # --- #

    is_successful = await_completion(opts)

    # --- #

    return save_artifacts(is_successful)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted ...")
        sys.exit(1)
