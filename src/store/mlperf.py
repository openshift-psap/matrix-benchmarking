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
            print(metric, ":", len(values))
        pass


def mlperf_parse_gpu_burn_results(dirname, import_settings):
    results = types.SimpleNamespace()

    try:
        with open(f"{dirname}/gpu_burn.log") as f:
            speed = 0
            for line in f.readlines():
                if "proc'd" not in line: continue
                speed = line.partition("(")[-1].partition(" ")[0]
            print()
            print(import_settings['gpu'], speed, "Gflop/s")
            results.speed = int(speed)

    except FileNotFoundError as e:
        print(f"{dirname}: Could not find 'gpu_burn.log' file ...")
        raise e

    return results

def mlperf_parse_ssd_results(dirname, import_settings):
    results = types.SimpleNamespace()

    try:
        with open(f"{dirname}/stdout") as f:
            for line in f.readlines():
                if "result=" in line:
                    results.exec_time = int(line.split('=')[-1].strip())
                if "avg. samples / sec" in line:
                    results.avg_sample_sec = float(line.split("avg. samples / sec: ")[-1].strip())

    except FileNotFoundError as e:
        print(f"{dirname}: Could not find 'stdout' file ...")
        raise e

    if import_settings['cores'] == "8":
        print("\t".join([str(import_settings[k]) for k in  sorted(import_settings)]), "\t", int(int(results.exec_time)/60), "min", "\t", results.avg_sample_sec, "avg. samples / sec")
    return results


def mlperf_parse_results(dirname, import_settings):
    PARSERS = {
        "ssd": mlperf_parse_ssd_results,
        "burn": mlperf_parse_gpu_burn_results
     }

    results = PARSERS[import_settings['benchmark']](dirname, import_settings)

    mlperf_parse_prom_gpu_metrics(dirname, results)

    return [({}, results)]

store.simple.custom_parse_results = mlperf_parse_results
