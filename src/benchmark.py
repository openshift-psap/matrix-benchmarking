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

DEFAULT_MODE =  "mlperf"
def main():
    mode = store.parse_argv(sys.argv[1:])
    store_plugin = store.mode_store(mode)

    dry = "run" in store.experiment_filter

    benchmark_desc_file = os.path.realpath(common.RESULTS_PATH
                                           + f"/{mode}/benchmarks.yaml")
    with open(benchmark_desc_file) as f:
        all_yaml_benchmark_desc = list(yaml.safe_load_all(f))

    exe = Exec(dry)

    exe.log("Loading previous matrix results: ... ")
    store_plugin.parse_data(mode)
    exe.log("Loading previous matrix results: done")

    for yaml_benchmark_desc in all_yaml_benchmark_desc:
        script_to_run = matrix.Matrix(mode, yaml_benchmark_desc)
        script_to_run.run(exe)

    return 0


if __name__ == "__main__":
    sys.exit(main())
