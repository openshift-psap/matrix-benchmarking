import types

import store.simple
from store.simple import *

def mlperf_rewrite_settings(params_dict):
    return params_dict

store.custom_rewrite_settings = mlperf_rewrite_settings


def mlperf_parse_results(dirname, import_settings):
    results = types.SimpleNamespace()

    try:
        with open(f"{dirname}/stdout") as f:
            for line in f.readlines():
                if "result=" in line:
                    results.timing = int(line.split('=')[-1].strip())
                if "avg. samples / sec" in line:
                    results.avg_sample_sec = float(line.split("avg. samples / sec: ")[-1].strip())
            results.stdout = f.read().strip()
    except FileNotFoundError as e:
        print(f"{dirname}: Could not find 'stdout' file ...")
        raise e

    if import_settings['cores'] == "8":
        print("\t".join([str(import_settings[k]) for k in  sorted(import_settings)]), "\t", int(int(results.timing)/60), "min", "\t", results.avg_sample_sec, "avg. samples / sec")
    return [({}, results)]

store.simple.custom_parse_results = mlperf_parse_results
