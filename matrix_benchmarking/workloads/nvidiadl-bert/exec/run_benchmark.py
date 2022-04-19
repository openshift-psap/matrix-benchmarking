#! /usr/bin/env python3

import os, sys
import urllib3
import types
import pathlib
import yaml
import time
import json
import logging
import datetime

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"),
                    format="%(levelname)s | %(message)s",)

import common
import kube

TEMPLATE = pathlib.Path(__file__).parent / "mpijob_run-bert_template.j2.yaml"
NAMESPACE = "matrix-benchmarking"
BENCHMARK_NAME = pathlib.Path(__file__).parent.parent.name

state = types.SimpleNamespace()

def on_benchmark_start():
    common.create_artifact_dir(BENCHMARK_NAME)

    with common.time_it("on_benchmark_start::do_cleanup"):
        do_cleanup()

    state.prom_data = common.prepare_prometheus()

def on_benchmark_end():
    common.finalize_prometheus(state.prom_data)

    do_cleanup()

    common.save_system_artifacts()

    logging.info("Artifacts saved into %s", common._artifacts_dir)

    return True

def do_cleanup():
    #common.delete_all_resources(["MPIJobs", "Pods"])
    logging.info("Delete all the MPIJobs of the namespace ...")
    mpijobs = kube.custom.list_namespaced_custom_object("kubeflow.org", "v2beta1", state.namespace, "mpijobs")
    for mpijob in mpijobs["items"]:
        try:
            kube.custom.delete_namespaced_custom_object("kubeflow.org", "v2beta1", state.namespace, "mpijobs", mpijob["metadata"]["name"])
        except kube.kubernetes.client.exceptions.ApiException as e:
            if e.reason != "Not Found": raise e

    logging.info("Delete all the Pods of the namespace ...")
    first = True
    while True:
        pods = kube.corev1.list_namespaced_pod(namespace=state.namespace)
        if len(pods.items) == 0:
            if not first:
                logging.info("Done, all the Pods have been deleted.")
            break

        if first:
            logging.info("Found pods still alive ...")
            first = False

        deleting_pods = []
        for pod in pods.items:
            try:
                kube.corev1.delete_namespaced_pod(namespace=state.namespace, name=pod.metadata.name)
                deleting_pods.append(pod.metadata.name)
            except kube.kubernetes.client.exceptions.ApiException as e:
                if e.reason != "Not Found": raise e

        if not deleting_pods:
            logging.info("Done, all the Pods have been deleted.")
            break

        logging.info(f"Deleting {len(deleting_pods)} Pods: %s", " ".join(deleting_pods))
        time.sleep(5)


def do_launch():
    generated_document, yaml_docs = common.apply_yaml_template(TEMPLATE, state.settings.__dict__)
    common.save_artifact(generated_document, "resources.generated.yaml", is_src=True)

    mpijob_yaml = yaml_docs[0]

    state.mpijob_name = mpijob_yaml["metadata"]["name"]

    group, version = mpijob_yaml["apiVersion"].split("/")

    kube.custom.create_namespaced_custom_object(
        group, version, state.namespace, "mpijobs",
        mpijob_yaml
    )


def wait_execution_completion():
    logging.info(f"%s | Waiting for {state.mpijob_name} to complete its execution ...", datetime.datetime.now().strftime("%H:%M:%S"))
    logging.info(f"Delete the MPIJob/{state.mpijob_name} to interrupt (and fail) the wait.")

    had_mpijob = False
    failed = False
    while not failed:
        time.sleep(5)
        try:
            mpijob = kube.custom.get_namespaced_custom_object("kubeflow.org", "v1",
                                                              state.namespace, "mpijobs", state.mpijob_name)
            had_mpijob = True
        except kube.kubernetes.client.exceptions.ApiException as e:
            if e.reason != "Not Found": raise e
            if had_mpijob:
                logging.error("MPIJob has been deleted")
            else:
                logging.error("MPIJob doesn't exist, that's unexpected ...")

            failed = True

            break

        status = mpijob.get("status")
        if status and status.get("completionTime"):
            break

        pods = kube.corev1.list_namespaced_pod(namespace=state.namespace,
                                  label_selector=f"training.kubeflow.org/job-name={state.mpijob_name}")
        for pod in pods.items:
            try:
                if pod.status.container_statuses[0].state.waiting.reason == "ImagePullBackOff":
                    logging.error(f"Pod {pod.metadata.name} is in state ImagePullBackOff. Aborting")
                    failed = True
            except Exception: pass

            try:
                if pod.status.container_statuses[0].state.terminated.reason == "Error":
                    logging.error(f"Pod {pod.metadata.name} is in state Error. Aborting")
                    failed = True
            except Exception: pass

    logging.info("Done waiting for the execution completion. %s", "Failed" if failed else "Success")
    return not failed


def do_save_mpi_artifacts():
    failed = False

    def save_yaml(obj, filename):
        obj_dict = obj if isinstance(obj, dict) else obj.to_dict()

        common.save_artifact(yaml.dump(obj_dict), filename)

    mpijob = kube.custom.get_namespaced_custom_object("kubeflow.org", "v1",
                                                   state.namespace, "mpijobs", state.mpijob_name)
    save_yaml(mpijob, "mpijob.status.yaml")

    pods = kube.corev1.list_namespaced_pod(namespace=state.namespace,
                                           label_selector=f"training.kubeflow.org/job-name={state.mpijob_name}")
    save_yaml(pods, "pods.status.yaml")
    for pod in pods.items:
        phase = pod.status.phase

        logging.info(f"{pod.metadata.name} --> {phase}")
        try:
            logs = kube.corev1.read_namespaced_pod_log(namespace=state.namespace, name=pod.metadata.name)
        except kube.kubernetes.client.exceptions.ApiException as e:
            logging.error(f"Could not get Pod {pod.metadata.name} logs: %s", json.loads(e.body))
            logs = str(e)

        common.save_artifact(logs, f"pod.{pod.metadata.name}.log")

        if pod.metadata.labels["training.kubeflow.org/job-role"] == "launcher":
            if phase != "Succeeded":
                failed = True
        elif pod.metadata.labels["training.kubeflow.org/job-role"] == "worker":
            if phase == "Error":
                failed = True

    return not failed


def main():
    state.settings = common.prepare_settings()
    state.namespace = NAMESPACE

    logging.info("Testing cluster connectivity ...")
    if not common.is_connected():
        logging.error("Not connected to the cluster, aborting.")
        return False

    try:
        on_benchmark_start()

        do_launch()

    except Exception as e:
        logging.error("Caught an exception during launch time, aborting.")
        raise e

    try:
        with common.time_it("wait_execution_completion"):
            wait_success = wait_execution_completion()
    except KeyboardInterrupt as err:
        print("\n")
        logging.error("Keyboard Interrupted :/")
        return 1

    try:
        steps_success = {
            "execution": wait_success,
            "execution artifacts": do_save_mpi_artifacts(),
            "tear-down": on_benchmark_end()
        }
    except Exception as e:
        logging.error("Caught an exception during tear-down time...")
        raise e

    success = False not in steps_success.values()
    if not success:
        logging.info("Failures detected ...")
        for k, v in success.items():
            if v: continue
            logging.info(f"- {k}")

    return 0 if success else 1

if __name__ == "__main__":
    try:
        with common.time_it("script execution"):
            sys.exit(main())
    except KeyboardInterrupt:
        print("\n")
        logging.error("Interrupted :/")
        sys.exit(1)
