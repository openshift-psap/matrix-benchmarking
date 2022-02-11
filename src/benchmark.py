import os, sys
import pathlib

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
    store.experiment_flags["--benchmark-mode"] = True

    if len(sys.argv) == 1:
        print("ERROR: please pass the benchmark file in first parameter.")
        return 1

    benchmark_desc_file = pathlib.Path(os.path.realpath(sys.argv[1]))

    if not benchmark_desc_file.exists():
        print("ERROR: please pass the benchmark file in first parameter.")
        return 1

    try:
        print(f"Loading the benchmark file {sys.argv[1]} ...")
        with open(benchmark_desc_file) as f:
            yaml_benchmark_desc = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse the benchmark file {benchmark_desc_file}.")
        raise e

    store.load_benchmark_file_flags(yaml_benchmark_desc)
    store.parse_argv(sys.argv[2:])

    results_dirname = store.experiment_flags["--results-dirname"]
    if not results_dirname:
        results_dirname = yaml_benchmark_desc.get("--results-dirname")

    if not results_dirname:
        print(f"ERROR: No results_dirname available in CLI or in the benchmark file.")
        return 1

    workload_store = store.load_store()

    dry = not store.experiment_flags["--run"]
    exe = Exec(dry)

    if store.experiment_flags["--clean"]:
        store.experiment_flags["--parse-only"] = True
        if dry:
            print("INFO: Running the result directory cleaner in dry mode. Pass --run to perform the deletion.")
        else:
            print("INFO: Running the result directory cleaner...")

    exe.log(f"Loading previous results from {results_dirname} ... ")
    workload_store.parse_data(results_dirname)
    exe.log(f"Loading previous results: done, found {len(common.Matrix.processed_map)} results")
    if store.experiment_flags["--parse-only"]:
        if not store.experiment_flags["--clean"]:
            if not dry:
                print("WARNING: --run has no effect if --parse-only is enabled.")

        return 0

    if exe.dry:
        exe.log("#")
        exe.log("# DRY RUN")
        exe.log("#")

    script_to_run = matrix.Matrix(results_dirname, yaml_benchmark_desc)
    script_to_run.run(exe)

    return 0


if __name__ == "__main__":
    sys.exit(main())
