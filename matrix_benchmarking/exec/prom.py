import types
import logging
import base64
import time
import datetime
import math

logging.info("Importing prometheus_api_client ...")
import prometheus_api_client

import matrix_benchmarking.kube as kube

def _get_secret_token():
    logging.info("Prometheus: Fetching the monitoring secret token ...")

    secrets = kube.corev1.list_namespaced_secret(namespace="openshift-user-workload-monitoring")
    for secret in secrets.items:
        name = secret.metadata.name
        if not name.startswith("prometheus-user-workload-token"):
            continue
        return base64.b64decode(secret.data["token"]).decode("ascii")

    return ""


def _get_thanos_hostname():
    logging.info("Prometheus: Fetching the route URL ...")

    thanos_querier_route = kube.custom.get_namespaced_custom_object(
        group="route.openshift.io", version="v1",
        namespace="openshift-monitoring", plural="routes",
        name="thanos-querier")

    return thanos_querier_route["spec"]["host"]


def _has_user_monitoring():
    logging.info("Prometheus: Checking if user-monitoring is enabled ...")
    try:
        monitoring_cm = kube.corev1.read_namespaced_config_map(namespace="openshift-monitoring",
                                                               name="cluster-monitoring-config")
        cfg = monitoring_cm.data["config.yaml"]

        return "enableUserWorkload: true" in cfg
    except kube.kubernetes.client.exceptions.ApiException as e:
        if e.reason != "Not Found":
            raise e
        return False
    except KeyError:
        return False


def _get_prometheus_podinfo():
    PROM_POD_LABEL = "app.kubernetes.io/component=prometheus"

    podinfo = types.SimpleNamespace()
    podinfo.container = "prometheus"

    podinfo.namespace = "openshift-monitoring"

    pods = kube.corev1.list_namespaced_pod(namespace=podinfo.namespace,
                                           label_selector=PROM_POD_LABEL)

    if not pods.items:
        raise RuntimeError(f"Pod {label} not found in {namespace} ...")

    podinfo.podname = pods.items[0].metadata.name

    return podinfo


def _get_PrometheusConnect(handler):
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    headers = dict(Authorization=f"Bearer {handler.token}")
    return prometheus_api_client.PrometheusConnect(url=f"https://{handler.host}",
                                                   headers=headers, disable_ssl=True,)


def _exec_in_pod(namespace, podname, container, cmd):
    exec_command = ['/bin/sh', '-c', cmd]

    return kube.k8s_stream(
        kube.corev1.connect_get_namespaced_pod_exec,
        namespace=namespace,
        command=exec_command,
        name=podname,
        container=container,
        stderr=False, stdin=False, stdout=True, tty=False,
    )

def do_query(handler, api_cmd, **data):
    if not handler.token:
        raise RuntimeError("Prometheus token not available ...")

    url = f"https://{handler.host}/api/v1/{api_cmd}"
    encoded_data = urllib.parse.urlencode(data)
    url += "?" + encoded_data

    curl_cmd = f"curl --silent -k '{url}' --header 'Authorization: Bearer {handler.token}'"

    resp = _exec_in_pod(handler.prom_podinfo.namespace, handler.prom_podinfo.podname,
                        handler.prom_podinfo.container, curl_cmd)

    result = json.loads(resp.replace("'", '"'))

    if result["status"] == "success":
        return result["data"]


def get_handler():
    if not _has_user_monitoring():
        logging.error("""User monitoring not enabled. See https://docs.openshift.com/container-platform/4.10/monitoring/enabling-monitoring-for-user-defined-projects.html#enabling-monitoring-for-user-defined-projects_enabling-monitoring-for-user-defined-projects""")
        raise SystemExit(1)

    handler = types.SimpleNamespace()

    handler.token = _get_secret_token()
    handler.host = _get_thanos_hostname()
    handler.prom_podinfo = _get_prometheus_podinfo()
    handler.prom_connect = _get_PrometheusConnect(handler)

    return handler


def restart_prometheus():
    prom_podinfo = _get_prometheus_podinfo()
    handler = get_handler()

    logging.info("Stopping Prometheus Pod ...")
    kube.corev1.delete_namespaced_pod(prom_podinfo.podname, prom_podinfo.namespace)

    while True:
        logging.info("Waiting for Prometheus Pod to be recreated ...")

        try:
            handler.prom_podinfo =_get_prometheus_podinfo()
        except RuntimeError:
            time.sleep(1)
            continue

        break # Prometheus Pod exists


    logging.info(f"Prometheus Pod is running again.")

    logging.info("Waiting for Prometheus to respond properly ...")
    while True:
        try:
            if query_current_ts(handler) is not None:
                    break
        except kube.kubernetes.client.exceptions.ApiException as e:
            if not "500" in e.reason:
                raise e
        except json.JSONDecodeError as e:
            pass # ignore

        time.sleep(1)

    return handler


def dump_prometheus_db_raw(handler):
    resp = _exec_in_pod(handler.prom_podinfo.namespace, handler.prom_podinfo.podname, handler.prom_podinfo.container,
                       "tar cvzf - /prometheus | base64")

    return base64.standard_b64decode(resp)


def query_current_ts(handler):
    try:
        metric = handler.prom_connect.get_current_metric_value(metric_name="cluster:memory_usage:ratio")
        return metric[0]["value"][0]
    except IndexError:
        return None


def query_values(handler, metric, ts_start, ts_stop):
    minutes = math.ceil((datetime.datetime.fromtimestamp(ts_stop) - datetime.datetime.fromtimestamp(ts_start)).seconds / 60)
    return handler.prom_connect.custom_query(query=f"{metric}[{minutes}m]", params=dict(time=ts_stop))


def dump_prometheus_db_json(handler, start_ts, stop_ts):
    all_metrics = handler.prom_connect.all_metrics()

    def chunker(seq, size):
        return (seq[pos:pos + size] for pos in range(0, len(seq), size))

    results = []
    current_group = all_metrics[1]
    last_metric = all_metrics[-1]
    for metric in all_metrics:
        current_group += f"|{metric}"
        # when the request size is longer that 21300 chars, we get an error 'HTTP Status Code 400 | Bad request'
        if len(current_group) < 20000 and metric != last_metric:
            continue

        results.append(query_values(handler, f'{{__name__=~"{current_group}"}}', start_ts, stop_ts))
        logging.info(f"{len(results)}) Found {len(results[-1])} new values")
        current_group = metric

    return results
