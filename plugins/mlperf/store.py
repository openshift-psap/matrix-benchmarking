import types

import store
import store.simple
from store.simple import *
import glob
import json
from collections import defaultdict

def mlperf_rewrite_settings(params_dict):
    params_dict.pop("opts", True)
    if params_dict["gpu_type"] == "full":
        params_dict["mig_strategy"] = "none"

    params_dict.pop("mig_label", True)
    if "mig_strategy" not in params_dict:
        params_dict["mig_strategy"] = "mixed"

    if "run" in params_dict:
        params_dict["@run"] = params_dict["run"]
        del params_dict["run"]

    return params_dict

store.custom_rewrite_settings = mlperf_rewrite_settings

def mlperf_parse_prom_gpu_metrics(dirname, results):
    return
    prom = results.prom = defaultdict(lambda: defaultdict(dict))
    for res_file in glob.glob(f"{dirname}/metrics/prom_*.json"):
        with open(res_file) as f:
            data = json.load(f)

        for result_per_gpu in data['result']:
            try: exported_pod = result_per_gpu["metric"]["exported_pod"]
            except KeyError: continue

            if exported_pod not in results.pod_names:
                continue

            if 'gpu' in result_per_gpu['metric']:
                gpu = result_per_gpu['metric']['gpu']
                prom_group = f"{exported_pod} | gpu #{gpu} "
            else:
                prom_group = "container"

            metric = result_per_gpu['metric']['__name__']
            values = [[ts, float(val)] for ts, val in result_per_gpu['values']]

            prom[metric][prom_group] = values
            #print(metric, ":", len(values))
        pass


def _parse_pod_logs(dirname, results, pod_logs_f):
    has_thr020 = {}
    prev_thr = {}
    #start_ts = None
    start_timestamps = {}

    for line in pod_logs_f.readlines():
        if "result=" in line:
            results.exec_time = int(line.split('=')[-1].strip())/60

        if "avg. samples / sec" in line:
            gpu_name = "single" if not line.startswith("/tmp") else \
                line.split(":")[0]

            results.avg_sample_sec[gpu_name] = float(line.split("avg. samples / sec: ")[-1].strip())

        if '"key": "eval_accuracy"' in line or '"key": "init_start"' in line:
            MLLOG_PREFIX = ":::MLLOG "
            if line.startswith(MLLOG_PREFIX):
                gpu_name = "full_gpu"
            else:
                gpu_name = line.partition(MLLOG_PREFIX)[0]

            json_content = json.loads(line.partition(MLLOG_PREFIX)[-1])
            line_ts = json_content['time_ms']

            if json_content['key'] == "eval_accuracy":
                if gpu_name in has_thr020: continue
                line_threshold = json_content['value']
                if line_threshold < prev_thr.get(gpu_name, 0): continue
                prev_thr[gpu_name] = line_threshold
                try:
                    threadhold_time = line_ts - start_timestamps[gpu_name]
                    results.thresholds[gpu_name].append([line_threshold, threadhold_time])
                    if line_threshold > 0.2: has_thr020[gpu_name] = True
                except KeyError:
                    raise Exception(f"gpu_name={gpu_name} didn't start in {pod_logs_f.name}")

            elif json_content['key'] == "init_start":
                if gpu_name in start_timestamps:
                    if gpu_name != "full_gpu":
                        raise Exception(f"Duplicated gpu_name={gpu_name} found in {pod_logs_f.name}")
                    else:
                        # running with in multi-GPU mode,
                        # keep only the 1st timestamp
                        continue

                start_timestamps[gpu_name] = line_ts

                results.thresholds[gpu_name] = []

def mlperf_parse_ssd_results(dirname, import_settings):
    results = types.SimpleNamespace()
    results.pod_names = set()
    results.thresholds = {}
    results.avg_sample_sec = {}

    has_logs = False
    for log_file in glob.glob(f"{dirname}/run-*.log"):
        pod_name = log_file.rpartition("/")[-1][:-4]
        results.pod_names.add(pod_name)
        with open(log_file) as log_f:
            try:
                _parse_pod_logs(dirname, results, log_f)
                has_logs = True
            except Exception as e:
                print(f"WARNING: failed to parse {log_file}: {e}")
                #raise e

    if not has_logs:
        print(f"WARNING: could not find pod log files in '{dirname}', skipping ...")
        return None

    return results


def mlperf_parse_results(dirname, import_settings):
    benchmark = import_settings.get("benchmark")
    if benchmark == "ssd":
        results = mlperf_parse_ssd_results(dirname, import_settings)
    else:
        print(f"WARNING: benchmark '{benchmark}' not currently parsed. Skipping {dirname} ...")
        results = None

    if results is None:
        return [({}, {})]

    if not store.benchmark_mode:
        mlperf_parse_prom_gpu_metrics(dirname, results)

    return [({}, results)]

store.simple.custom_parse_results = mlperf_parse_results
