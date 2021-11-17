import types

import store.simple
from store.simple import *
import glob
import json
from collections import defaultdict

def mlperf_rewrite_settings(params_dict):
    run = params_dict['run']
    del params_dict['run']
    params_dict['@run'] = run

    if params_dict['benchmark'] == "ssd":
        params_dict['threshold'] = f"{float(params_dict['threshold']):.03f}"
        if float(params_dict['threshold']) < 0.22: return {}

    return params_dict

store.custom_rewrite_settings = mlperf_rewrite_settings

def mlperf_parse_prom_gpu_metrics(dirname, results):
    prom = results.prom = defaultdict(lambda: defaultdict(dict))
    for res_file in glob.glob(f"{dirname}/prom_*.json"):
        with open(res_file) as f:
            data = json.load(f)
        for result_per_gpu in data['result']:
            if 'gpu' in result_per_gpu['metric']:
                gpu = result_per_gpu['metric']['gpu']
                prom_group = f"gpu#{gpu}"
            else:
                prom_group = "container"

            metric = result_per_gpu['metric']['__name__']
            values = [[ts, float(val)] for ts, val in result_per_gpu['values']]

            prom[metric][prom_group] = values
            #print(metric, ":", len(values))
        pass


def mlperf_parse_gpu_burn_results(dirname, import_settings):
    results = types.SimpleNamespace()

    try:
        with open(f"{dirname}/gpu_burn.log") as f:
            speed = 0
            for line in f.readlines():
                if "proc'd" not in line: continue
                speed = line.partition("(")[-1].partition(" ")[0]
            #print()
            #print(import_settings['gpu'], speed, "Gflop/s")
            results.speed = int(speed)

    except FileNotFoundError as e:
        print(f"{dirname}: Could not find 'gpu_burn.log' file ...")
        raise e

    return results

def mlperf_parse_ssd_results(dirname, import_settings):
    results = types.SimpleNamespace()

    #start_ts = None
    start_timestamps = {}
    results.thresholds = {}
    results.avg_sample_sec = {}

    if import_settings.get("threshold") != "0.23": return

    try:
        with open(f"{dirname}/pod.logs") as f:
            has_thr020 = {}
            prev_thr = {}

            for line in f.readlines():
                if "result=" in line:
                    results.exec_time = int(line.split('=')[-1].strip())/60

                if "avg. samples / sec" in line:
                    gpu_name = "single" if not line.startswith("/tmp") else \
                        line.split(":")[0]

                    results.avg_sample_sec[gpu_name] = float(line.split("avg. samples / sec: ")[-1].strip())

                if '"key": "eval_accuracy"' in line or '"key": "init_start"' in line:
                    MLLOG_PREFIX = ":::MLLOG "
                    if line.startswith(MLLOG_PREFIX):
                        gpu_name = "single_gpu"
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
                            raise Exception(f"gpu_name={gpu_name} didn't start in {dirname}/pod.logs")

                    elif json_content['key'] == "init_start":
                        if gpu_name in start_timestamps:
                            raise Exception(f"Duplicated gpu_name={gpu_name} found in {dirname}/pod.logs")
                        start_timestamps[gpu_name] = line_ts
                        #if start_ts is None:
                        #    start_ts = line_ts

                        results.thresholds[gpu_name] = []

    except FileNotFoundError as e:
        print(f"{dirname}: Could not find 'pod.logs' file ...")
        #raise e

    return results


def mlperf_parse_results(dirname, import_settings):
    PARSERS = {
        "ssd": mlperf_parse_ssd_results,
        "burn": mlperf_parse_gpu_burn_results
     }

    results = PARSERS[import_settings['benchmark']](dirname, import_settings)
    if results is None:
        return [({}, {})]

    mlperf_parse_prom_gpu_metrics(dirname, results)

    return [({}, results)]

store.simple.custom_parse_results = mlperf_parse_results
