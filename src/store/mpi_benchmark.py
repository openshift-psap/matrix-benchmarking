import store
import store.simple
from store.simple import *

def mpi_benchmark_rewrite_settings(params_dict):
    return params_dict

store.simple.custom_rewrite_settings = mpi_benchmark_rewrite_settings

def __parse_linpack(fname, entry):
    in_summary = False
    is_next = False

    avg_lst = entry.results.avg = []
    max_lst = entry.results.maxi = []

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

def __parse_sysbench_cpu(fname, entry):
    with open(fname) as f:
        evt_per_sec = None
        for _line in f:
            line = _line.strip()
            if line.startswith("events per second"):
                evt_per_sec = float(line.split(":")[-1].strip())

    entry.results.cpu_evt_per_sec = evt_per_sec

def __parse_sysbench_fio(fname, entry):
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

    entry.results.fio_thput_read = thput_read
    entry.results.fio_thput_write = thput_write

def __parse_osu(fname, entry):
    entry.results.osu_results = {}
    entry.results.osu_title = None
    entry.results.osu_legend = None

    with open(fname) as f:
        for _line in f:
            line = _line.strip()
            if line == "TIMEOUT": break
            if not line: continue

            if line.startswith('#'):
                if entry.results.osu_title is None:
                    entry.results.osu_title = line[1:].strip()
                elif entry.results.osu_legend is None:
                    entry.results.osu_legend = line[1:].strip()
                continue
            else:
                x, y = line.strip().split()
                entry.results.osu_results[int(x)] = float(y)


def mpi_benchmark_parse_results(dirname, entry):
    fname = f"{dirname}/stdout"

    try:
        benchmark, _, flavor = entry.params.benchmark.partition(".")
    except AttributeError as e:
        print(f"ERROR: Failed to parse {entry.location}")
        print("ERROR: --> no benchmark property ...")
        return
    except Exception as e:
        print(f"ERROR: Failed to parse benchmark name in {entry.location} ({entry.params.benchmark})")
        return
    {
        "linpack": __parse_linpack,
        "sysbench-cpu": __parse_sysbench_cpu,
        "sysbench-fio": __parse_sysbench_fio,
        "osu": __parse_osu,
    }[benchmark](fname, entry)


store.simple.custom_parse_results = mpi_benchmark_parse_results
