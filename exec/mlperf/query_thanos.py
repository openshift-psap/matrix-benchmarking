#! /usr/bin/python3

import subprocess
import urllib.request
import urllib.parse
import json
import ssl
import base64

import kubernetes.client
import kubernetes.config
import kubernetes.utils
from kubernetes.stream import stream as k8s_stream

kubernetes.config.load_kube_config()

v1 = kubernetes.client.CoreV1Api()
customv1 = kubernetes.client.CustomObjectsApi()

THANOS_CLUSTER_ROUTE = None # "thanos-querier-openshift-monitoring.apps.nvidia-test.nvidia-ocp.net"

def has_user_monitoring():
    print("Thanos: Checking if user-monitoring is enabled ...")
    try:
        monitoring_cm = v1.read_namespaced_config_map(namespace="openshift-monitoring",
                                                      name="cluster-monitoring-config")
        cfg = monitoring_cm.data["config.yaml"]

        return "enableUserWorkload: true" in cfg
    except kubernetes.client.exceptions.ApiException as e:
        if e.reason != "Not Found":
            raise e
        return False
    except KeyError:
        return False


def get_secret_token():
    print("Thanos: Fetching the monitoring secret token ...")
    secrets = v1.list_namespaced_secret(namespace="openshift-user-workload-monitoring")
    for secret in secrets.items:
        name = secret.metadata.name
        if not name.startswith("prometheus-user-workload-token"):
            continue

        return base64.b64decode(secret.data["token"]).decode("ascii")

    return ""

def get_thanos_hostname():
    if THANOS_CLUSTER_ROUTE:
        return THANOS_CLUSTER_ROUTE

    print("Thanos: Fetching the route URL ...")
    thanos_querier_route = customv1.get_namespaced_custom_object(group="route.openshift.io", version="v1",
                                                                 namespace="openshift-monitoring", plural="routes",
                                                                 name="thanos-querier")
    return thanos_querier_route["spec"]["host"]

def get_dcgm_podname():
    namespace = "nvidia-gpu-operator"
    label = "app=nvidia-dcgm-exporter"

    pods = v1.list_namespaced_pod(namespace=namespace, label_selector=label)
    if not pods.items:
        raise RuntimeError(f"Pod {label} not found in {namespace} ...")

    return pods.items[0].metadata.name

def _do_query(thanos, api_cmd, **data):
    if not thanos['token']:
        raise RuntimeError("Thanos token not available ...")

    url = f"https://{thanos['host']}/api/v1/{api_cmd}"
    encoded_data = urllib.parse.urlencode(data)
    url += "?" + encoded_data

    curl_cmd = f"curl --silent -k '{url}' --header 'Authorization: Bearer {thanos['token']}'"
    resp = exec_in_pod("nvidia-gpu-operator", thanos["pod_name"], curl_cmd)

    result = json.loads(resp.replace("'", '"'))

    if result["status"] == "success":
        return result["data"]

def query_current_ts(thanos):
    try:
        return _do_query(thanos, "query", query="cluster:memory_usage:ratio")['result'][0]['value'][0]
    except IndexError:
        return None


def query_metrics(thanos):
    return _do_query(thanos, "label/__name__/values")

def query_values(thanos, metrics, ts_start, ts_stop):
    #print(f"Get thanos metrics for '{metrics}' between {ts_start} and {ts_stop}.")
    return _do_query(thanos, "query_range",
                     query=metrics,
                     start=ts_start,
                     end=ts_stop,
                     step=1)


def exec_in_pod(namespace, name, cmd):
    # Calling exec and waiting for response
    exec_command = ['/bin/sh', '-c', cmd]

    return k8s_stream(v1.connect_get_namespaced_pod_exec,
                      name=name, namespace=namespace,
                      command=exec_command,
                      stderr=False, stdin=False,
                      stdout=True, tty=False)

def prepare_thanos():
    if not has_user_monitoring():
        raise Exception("""Thanos monitoring not enabled. See https://docs.openshift.com/container-platform/4.7/monitoring/enabling-monitoring-for-user-defined-projects.html#enabling-monitoring-for-user-defined-projects_enabling-monitoring-for-user-defined-projects""")

    return dict(
        token = get_secret_token(),
        host = get_thanos_hostname(),
        pod_name = get_dcgm_podname(),
    )

if __name__ == "__main__":
    thanos = prepare_thanos()
    #metrics = query_metrics(thanos)
    ts_start = 1637669864.153
    ts_stop = 1637669864.153

    if ts_start is None:
        ts_start = query_current_ts(thanos)
        import time
        time.sleep(10)
    if ts_start is None:
        ts_stop = query_current_ts(thanos)

    #values = query_values(thanos, "cluster:memory_usage:ratio", ts_start, ts_stop)
    #print(values)
    try:
        for metrics in ["DCGM_FI_DEV_POWER_USAGE",]:
            thanos_values = query_values(thanos, metrics, ts_start, ts_stop)
            if not thanos_values:
                print("No metric values collected for {metrics}")
                continue

            results = thanos_values['result']
            if not results:
                print(f"Found no result for {metrics} ...")
                continue

            print(f"Found {len(thanos_values['result'][0]['values'])} values for {metrics}")
            print(thanos_values['result'])
    except Exception as e:
        print(f"WARNING: Failed to save {metrics} logs:")
        print(f"WARNING: {e.__class__.__name__}: {e}")
        raise e
        pass
