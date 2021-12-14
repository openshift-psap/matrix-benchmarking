import os, sys

import yaml

import matrix
import store
import common

class Exec():
    def __init__(self, dry):
        self.dry = dry

    def log(self, *msg):
        print("INFO:", *msg)

def main():
    store.benchmark_mode = True

    mode = store.parse_argv(sys.argv[1:])
    store_plugin = store.mode_store(mode)

    benchmark_desc_file = os.path.realpath(common.RESULTS_PATH
                                           + f"/{mode}/benchmarks.yaml")
    with open(benchmark_desc_file) as f:
        all_yaml_benchmark_desc = list(yaml.safe_load_all(f))

    dry = not store.experiment_filter.pop("__run__", False)
    exe = Exec(dry)

    exe.log("Loading previous matrix results: ... ")
    store_plugin.parse_data(mode)
    exe.log("Loading previous matrix results: done")

    if store.experiment_filter.pop("__parse_only__", False):
        return 0

    if exe.dry:
        exe.log("#")
        exe.log("# DRY RUN")
        exe.log("#")

    for yaml_benchmark_desc in all_yaml_benchmark_desc:
        script_to_run = matrix.Matrix(mode, yaml_benchmark_desc)
        script_to_run.run(exe)

    return 0


if __name__ == "__main__":
    sys.exit(main())
