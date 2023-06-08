from collections import defaultdict
import statistics as stats

def filter_value_in_label(metrics, value, label):
    for metric in metrics:
        label_value = metric.metric.get(label)
        if label_value is None: continue
        if value not in label_value: continue

        # found it
        yield metric


def filter_doesnt_have_label(metrics, label):
    for metric in metrics:
        if label in metric.metric: continue

        yield metric

# ---

def mean(metrics, filter_fct):
    values = []
    for metric in filter_fct(metrics):
        values.append(stats.mean([float(v) for ts, v in metric.values]))

    return values


def last(metrics, filter_fct):
    values = []
    for metric in filter_fct(metrics):
        values.append(float(metric.values[-1][1]))

    return values
