import types

import store
import store.simple
from store.simple import *

def mpi_benchmark_rewrite_settings(params_dict):
    benchmark = params_dict["benchmark"]
    if benchmark.startswith("sysbench-fio"):
        params_dict["@worker"] = params_dict["worker"]
        del params_dict["worker"]
    if params_dict["@run"] == "":
        params_dict["@run"] = "0"

    return params_dict

store.custom_rewrite_settings = mpi_benchmark_rewrite_settings

def __parse_linpack(fname, properties):
    results = types.SimpleNamespace()
    in_summary = False
    is_next = False

    avg_lst = results.avg = []
    max_lst = results.maxi = []

    with open(fname) as f:
        for _line in f:
            line = _line.strip()
            if "Performance Summary" in line:
                in_summary = True
                continue
            elif not in_summary: continue

            if line.startswith("Size"):
                is_next = True
                continue
            if not is_next: continue
            if not line: break

            # Size   LDA    Align.  Average  Maximal
            # 20000  20016  4       42.8123  42.8123
            size, lda, align, avg, maxi = line.split()

            avg_lst.append(float(avg))
            max_lst.append(float(maxi))
    return [({}, results)]

def __parse_sysbench_cpu(fname, properties):
    results = types.SimpleNamespace()
    with open(fname) as f:
        evt_per_sec = None
        for _line in f:
            line = _line.strip()
            if line.startswith("events per second"):
                evt_per_sec = float(line.split(":")[-1].strip())

    results.cpu_evt_per_sec = evt_per_sec
    return [({}, results)]

def __parse_sysbench_fio(fname, properties):
    results = types.SimpleNamespace()

    thput_read = None
    thput_write = None

    current_section = None
    with open(fname) as f:

        for _line in f:
            line = _line.strip()
            if line == "TIMEOUT": break

            if not _line.startswith(" "):
                current_section = line[:-1]
                continue

            key, _, _val = line.partition(":")
            if current_section != "Throughput": continue

            val = float(_val.strip())
            if val == 0.0: continue

            if key == "written, MiB/s":
                thput_write = val
            if key == "read, MiB/s":
                thput_read = val

    results.fio_thput_read = thput_read
    results.fio_thput_write = thput_write
    return [({}, results)]

def __parse_osu(fname, properties):
    all_results = []

    osu_title = None
    osu_legend = None

    with open(fname) as f:
        for _line in f:
            current_settings = {}
            current_results = types.SimpleNamespace()

            line = _line.strip()
            if line == "TIMEOUT": break
            if not line: continue

            if line.startswith('#'):
                if osu_title is None:
                    osu_title = line[1:].strip()
                elif osu_legend is None:
                    osu_legend = line[1:].strip()
                continue

            x, y = line.strip().split()

            field = " ".join(osu_legend.split())\
                       .partition(" ")[-1]\
                       .partition("(")[0]\
                       .strip()\
                       .replace(" ", "_")\
                       .lower()

            current_settings["message size"] = int(x)
            current_results.__dict__[field] = float(y)
            current_results.osu_title = osu_title
            current_results.osu_legend = osu_legend

            all_results.append([current_settings, current_results])

    return all_results

def mpi_benchmark_parse_results(dirname, properties):
    fname = f"{dirname}/stdout"

    try:
        benchmark, _, flavor = properties["benchmark"].partition(".")
    except AttributeError as e:
        print(f"ERROR: Failed to parse {dirname}: --> no benchmark property ...")
        return
    except Exception as e:
        print(f"ERROR: Failed to parse benchmark name in {dirname} "
              "({properties['benchmark']})")
        return

    fct = {
        "linpack": __parse_linpack,
        "sysbench-cpu": __parse_sysbench_cpu,
        "sysbench-fio": __parse_sysbench_fio,
        "osu": __parse_osu,
    }[benchmark]

    return fct(fname, properties)


store.simple.custom_parse_results = mpi_benchmark_parse_results
