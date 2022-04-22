from collections import defaultdict
import statistics as stats

def mean(metrics, podname):
    values = []
    for metric in metrics:
        exported_pod = metric["metric"].get("exported_pod", "")
        pod = metric["metric"].get("pod", "")
        if podname not in exported_pod and podname not in pod: continue

        values.append(stats.mean([float(v) for ts, v in metric["values"]]))

    return values


def last(metrics, podname):
    values = []
    for metric in metrics:
        exported_pod = metric["metric"].get("exported_pod", "")
        pod = metric["metric"].get("pod", "")
        if podname not in exported_pod and podname not in pod: continue

        values.append(float(metric["values"][-1][1]))
    return values
