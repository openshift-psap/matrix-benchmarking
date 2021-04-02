#! /usr/bin/python3

import subprocess
import urllib.request
import urllib.parse
import json
import ssl

CMD_HAS_USER_MONITORING = "oc get cm/cluster-monitoring-config -n openshift-monitoring >/dev/null"

CMD_GET_SECRET_NAME = "oc get secret -n openshift-user-workload-monitoring \
                 | grep  prometheus-user-workload-token \
                 | head -n 1 \
                 | awk '{ print $1 }'"

CMD_GET_TOKEN = "oc get secret {} \
                -n openshift-user-workload-monitoring \
                -o jsonpath='{{@.data.token}}' \
           | base64 -d"

CMD_GET_THANOS_HOSTNAME = "oc get route thanos-querier \
                              -n openshift-monitoring  \
                              -o jsonpath='{@.spec.host}'"

def has_user_monitoring():
    try:
        subprocess.check_call(CMD_HAS_USER_MONITORING, shell=True)
        return True
    except subprocess.CalledProcessError:
        return False

def get_user_monitoring():
    return """\
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
"""

def get_secret_name():
    return subprocess.check_output(CMD_GET_SECRET_NAME, shell=True).decode('utf-8').strip()

def get_token(secret_name):
    return subprocess.check_output(CMD_GET_TOKEN.format(secret_name), shell=True).decode('utf-8')

THANOS_PROXY_PORT = "9988"
# ssh -N -L localhost:9988:thanos-querier-openshift-monitoring.apps.test.myocp4.com:443 nva100.ocp
# + add 127.0.0.1 thanos-querier-openshift-monitoring.apps.test.myocp4.com in /etc/hosts

def get_thanos_hostname():
    thanos_host = subprocess.check_output(CMD_GET_THANOS_HOSTNAME, shell=True).decode('utf-8')

    if thanos_host.endswith("test.myocp4.com"):
        thanos_host += f":{THANOS_PROXY_PORT}"

    return thanos_host

def _do_query(thanos, api_cmd, **data):
    url = f"https://{thanos['host']}/api/v1/{api_cmd}"
    encoded_data = urllib.parse.urlencode(data)
    url += "?" + encoded_data

    req = urllib.request.Request(url, method='GET',
                                 headers={f"Authorization": f"Bearer {thanos['token']}"})
    context = ssl._create_unverified_context()

    content = urllib.request.urlopen(req, context=context).read()
    return json.loads(content.decode('utf-8'))['data']

def query_current_ts(thanos):
    try:
        return _do_query(thanos, "query", query="cluster:memory_usage:ratio")['result'][0]['value'][0]
    except IndexError:
        return None


def query_metrics(thanos):
    return _do_query(thanos, "label/__name__/values")

def query_values(thanos, metrics, ts_start, ts_stop):
    print(f"Get thanos metrics for '{metrics}' between {ts_start} and {ts_stop}.")
    return _do_query(thanos, "query_range",
                     query=metrics,
                     start=ts_start,
                     end=ts_stop,
                     step=1)


def prepare_thanos():

    secret_name = get_secret_name()
    return dict(
        token = get_token(secret_name),
        host = get_thanos_hostname()
    )

if __name__ == "__main__":
    thanos = prepare_thanos()
    #metrics = query_metrics(thanos)
    ts_start = 1615198949.457
    ts_stop = 1615198979.53

    if ts_start is None:
        ts_start = query_current_ts(thanos)
        import time
        time.sleep(10)
    if ts_start is None:
        ts_stop = query_current_ts(thanos)

    #values = query_values(thanos, "cluster:memory_usage:ratio", ts_start, ts_stop)
    #print(values)
    try:
        for metrics in ["DCGM_FI_DEV_MEM_COPY_UTIL", "DCGM_FI_DEV_GPU_UTIL", "DCGM_FI_DEV_POWER_USAGE",
                    "cluster:cpu_usage_cores:sum",]:
            thanos_values = query_values(thanos, metrics, ts_start, ts_stop)
            if not thanos_values:
                print("No metric values collected for {metrics}")
                continue


            print(f"Found {len(thanos_values['result'][0]['values'])} values for {metrics}")
            print(thanos_values['result'])
    except Exception as e:
        print(f"WARNING: Failed to save {metrics} logs:")
        print(f"WARNING: {e.__class__.__name__}: {e}")
        raise e
        pass
