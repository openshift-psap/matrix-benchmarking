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
            results.word = f.read().strip()
    except FileNotFoundError as e:
        print(f"{dirname}: Could not find 'stdout' file ...")
        raise e
    return [({}, results)]

store.simple.custom_parse_results = mlperf_parse_results
