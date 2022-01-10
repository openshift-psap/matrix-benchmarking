import types
import store.simple
from store.simple import *

def rewrite_settings(params_dict):
    return params_dict

store.custom_rewrite_settings = rewrite_settings

def parse_gpu_burn_results(dirname, import_settings):
    results = types.SimpleNamespace()

    try:
        with open(f"{dirname}/pod.log") as f:
            speed = 0
            for line in f.readlines():
                if "proc'd" not in line: continue
                speed = line.partition("(")[-1].partition(" ")[0]

            results.speed = int(speed)

    except FileNotFoundError as e:
        print(f"{dirname}: Could not find 'pod.log' file ...")
        raise e

    return results

def parse_test_properties_results(dirname, import_settings):
    results = types.SimpleNamespace()
    try:
        with open(f"{dirname}/step_count") as f:
            results.step_count = int(f.read())

        with open(f"{dirname}/test_passed") as f:
            results.test_passed = int(f.read())

        with open(f"{dirname}/ansible_tasks_ok") as f:
            results.ansible_tasks_ok = int(f.read())

    except FileNotFoundError as e:
        print(f"{dirname}: Could not find 'pod.log' file ...")
        raise e

    return results

def parse_results(dirname, import_settings):
    PARSERS = {
        "gpu-burn": parse_gpu_burn_results,
        "test-properties": parse_test_properties_results,
    }

    try:
        benchmark = import_settings['benchmark']
    except KeyError as e:
        print(f"ERROR: benchmark setting missing in {dirname}")
        raise e

    try:
        parser = PARSERS[benchmark]
    except KeyError as e:
        print(f"ERROR: no parser for benchmark={benchmark} in {dirname}")
        raise e

    results = parser(dirname, import_settings)
    if results is None:
        return [({}, {})]

    return [({}, results)]


store.simple.custom_parse_results = parse_results
