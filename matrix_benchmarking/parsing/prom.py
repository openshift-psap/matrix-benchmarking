from collections import defaultdict
import statistics as stats

def filter_single(metrics):
    if len(metrics) != 1:
        raise ValueError(f"filter_single expected to find only one metric. Found {len(metrics)}")

    yield metrics[0]


def filter_all(metrics):
    yield from metrics


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
        values.append(stats.mean([float(v) for ts, v in metric.values.items()]))

    return values


def last(metrics, filter_fct):
    values = []
    for metric in filter_fct(metrics):
        values.append(float(list(metric.values.values())[-1]))

    return values

def max_(metrics, filter_fct):
    values = []
    for metric in filter_fct(metrics):
        values.append(max([float(v) for ts, v in metric.values.items()]))

    return values

# ---

def single_max(metrics):
    return max_(metrics, filter_single)

def single_mean(metrics):
    return mean(metrics, filter_single)

def single_last(metrics):
    return last(metrics, filter_single)

# ---

def all_max(metrics):
    return max_(metrics, filter_all)

def max_max(metrics):
    return max(max_(metrics, filter_all))
