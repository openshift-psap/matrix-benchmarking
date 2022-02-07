import types, datetime
import yaml

import store
import store.simple
from store.simple import *

def mpi_benchmark_rewrite_settings(params_dict):
    params_dict["@run"] = params_dict["run"]
    del params_dict["run"]

    if params_dict["@run"] == "":
        params_dict["@run"] = "0"

    mode = params_dict.pop("mode")
    op = params_dict.pop("operation")
    params_dict["operation"] = f"{mode}-{op}"

    if mode == "p2p":
        params_dict["node_count"] = "2"

    # remove expe setting
    expe = params_dict.pop("expe")

    return params_dict

store.custom_rewrite_settings = mpi_benchmark_rewrite_settings

def __parse_hello(dirname, settings):
    results = types.SimpleNamespace()

    with open(f"{dirname}/mpijob.status.yaml") as f:
        mpijob_status = yaml.safe_load(f)

    start = datetime.datetime.strptime(mpijob_status["status"]["startTime"] , "%Y-%m-%dT%H:%M:%SZ")
    stop = datetime.datetime.strptime(mpijob_status["status"]["completionTime"] , "%Y-%m-%dT%H:%M:%SZ")

    results.completionTime = stop - start

    return results

def __parse_osu(dirname, settings):
    results = types.SimpleNamespace()

    results.osu_title = None
    results.osu_legend = None
    results.measures = {}

    with open(f"{dirname}/mpijob.launcher.log") as f:
        for _line in f:

            current_results = types.SimpleNamespace()

            line = _line.strip()
            if line == "TIMEOUT": break
            if not line: continue
            if "Failed to add the host" in line: continue

            if line.startswith('#'):
                if results.osu_title is None:
                    results.osu_title = line[1:].strip()
                elif results.osu_legend is None:
                    results.osu_legend = line[1:].strip().split(maxsplit=1)
                else:
                    raise ValueError("Found too many comments ...")

                continue
            try:
                size, bw = line.strip().split()
                results.measures[int(size)] = float(bw)
            except ValueError as e:
                print(f"ERROR: Failed to parse the Launcher logs in {f.name}: {e}")
                print(line.strip())

    return results

def mpi_benchmark_parse_results(dirname, settings):
    mode = settings.get("mode")
    if not mode:
        print(f"ERROR: failed to parse '{dirname}', 'mode' setting not defined.")
        return

    mode_fct = {
        "p2p": __parse_osu,
        "collective":  __parse_osu,
        "hello":  __parse_hello,
    }

    fct = mode_fct.get(mode)
    if not fct:
        print(f"ERROR: failed to parse '{dirname}', mode={mode} not recognized.")
        return

    return [[{}, fct(dirname, settings)]]


store.simple.custom_parse_results = mpi_benchmark_parse_results
