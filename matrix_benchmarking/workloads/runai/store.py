import types, datetime
import yaml
from collections import defaultdict
import glob

import store
import store.simple
from store.simple import *


def runai_rewrite_settings(params_dict):
    # add a @ on top of parameter name 'run'
    # to treat it as multiple identical executions

    #params_dict["@run"] = params_dict["run"]
    #del params_dict["run"]

    params_dict["ngpu"] = int(params_dict.get("ngpu", 1))

    if params_dict.get("mode"):
        if params_dict.get("mode") == "training":
            params_dict["inference_count"] = "0"
            params_dict["inference_fraction"] = "0"
            params_dict["training_count"] = "1"
            params_dict["training_fraction"] = "1"
        else:
            params_dict["inference_count"] = "1"
            params_dict["inference_fraction"] = "1"
            params_dict["training_count"] = "0"
            params_dict["training_fraction"] = "0"

        params_dict["partionner"] = "native"
        del params_dict["mode"]

    try: del params_dict["inference_time"]
    except KeyError: pass

    return params_dict

def __parse_runai_gpu_burn(dirname, settings):
    results = types.SimpleNamespace()

    files = glob.glob(f"{dirname}/runai_gpu-burn*.log")
    log_filename = files[-1]
    if len(files) != 1:
        print("WARNING: found multiple log files in {dirname}.")
        print("         Taking the last one: '{log_filename}'.")

    speed = 0
    unit = ""
    with open(log_filename) as f:
        for line in f.readlines():
            if "proc'd" not in line: continue
            # 100.0%  proc'd: 27401 (3913 Gflop/s)   errors: 0   temps: 59 C
            speed = line.split()[3][1:]
            unit = line.split()[4][:1]

    results.speed = int(speed)
    results.unit = unit

    return results


def __parse_runai_ssd(dirname, settings):
    results = types.SimpleNamespace()
    results.oom =  defaultdict(lambda: False)
    results.runtime = {}
    results.training_speed = {}
    results.inference_speed = defaultdict(list)

    for fpath in glob.glob(f"{dirname}/*.log"):
        fname = fpath.rpartition("/")[-1]

        with open(fpath) as f:
            for line in f.readlines():
                if "Resource exhausted: OOM when allocating tensor" in line:
                    results.oom[fname] = True

                if line.startswith("Benchmark result:"):
                    results.inference_speed[fname].append(float(line.split()[-2])) # img/s
                if line.startswith("Single GPU mixed precision training performance"):
                    results.training_speed[fname] = float(line.split()[-2]) # img/s

    for fpath in glob.glob(f"{dirname}/pod_*.status.yaml"):
        fname = fpath.rpartition("/")[-1]
        if "inference" in fname:
            # inference jobs are interrupted, they don't have a runtime.
            continue

        with open(fpath) as f:
            try:
                pod = yaml.safe_load(f)
                state = pod["status"]["containerStatuses"][0]["state"]["terminated"]
                start = state["startedAt"]
                stop = state["finishedAt"]
                FMT = '%Y-%m-%dT%H:%M:%SZ'

                results.runtime[fname] = (datetime.datetime.strptime(stop, FMT) - datetime.datetime.strptime(start, FMT)).seconds

            except Exception as e:
                results.runtime[fname] = None

    return results

def runai_parse_results(dirname, settings):
    model = settings.get("model")
    if not model:
        model = settings.get("benchmark")

    if not model:
        print(f"ERROR: failed to parse '{dirname}', 'benchmark' setting not defined.")
        return

    model_fct = {
        "gpu-burn":  __parse_runai_gpu_burn,
        "ssd": __parse_runai_ssd,
    }

    fct = model_fct.get(model)
    if not fct:
        print(f"ERROR: failed to parse '{dirname}', model={model} not recognized.")
        return

    ret = fct(dirname, settings)
    if not ret: return None

    return [[{}, ret]]

store.custom_rewrite_settings = runai_rewrite_settings
store.simple.custom_parse_results = runai_parse_results
