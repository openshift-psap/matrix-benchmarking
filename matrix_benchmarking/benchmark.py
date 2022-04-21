import os, sys
import logging

import yaml

import matrix_benchmarking.store as store
import matrix_benchmarking.common as common
import matrix_benchmarking.matrix as matrix
import matrix_benchmarking.cli_args as cli_args

# default values must evaluate to False, otherwise they cannot be
# overriden in the benchmark file.
def main(workload: str = "",
         benchmark_file: str = "",
         results_dirname: str = "",
         run: bool = False,
         generate: bool = False,
         remote_mode: bool = False,
         path_tpl: str = None,
         script_tpl: str = None,
         stop_on_error: bool = False,
         expe_to_run: list[str] = [],
         filters: list[str] = [],
         ):
    """
Run MatrixBenchmarking benchmarking.

Run MatrixBenchmarking benchmarking.

Env:
    MATBENCH_WORKLOAD
    MATBENCH_BENCHMARK_FILE
    MATBENCH_RUN
    MATBENCH_RESULTS_DIRNAME
    MATBENCH_REMOTE_MODE
    MATBENCH_PATH_TPL
    MATBENCH_SCRIPT_TPL
    MATBENCH_STOP_ON_ERROR
    MATBENCH_EXPE_TO_RUN
    MATBENCH_FILTERS

See the `FLAGS` section for the descriptions.

Args:
    workload: Name of the workload to execute. (Mandatory.)
    benchmark_file: Path of the benchmark file to execute. (Mandatory.)

    run: If 'False', run in dry mode. If 'True', execute the benchmark.
    results_dirname: Name of the directory where the results will be stored. Can be set in the benchmark file. (Mandatory.)
    remote_mode: If 'True', generate a benchmark script, instead of running the benchmark locally. If 'False', run the benchmark locally (default). Can be set in the benchmark file.
    path_tpl: Path template for generating the directories where the benchmark results will be stored. Can be set in the benchmark file.
    script_tpl: Path template for the script to execute the benchmark. Can be set in the benchmark file.
    stop_on_error: If 'True', stop the matrix benchmarking execution on the first error. If 'False', ignore the error and continue. Can be set in the benchmark file.
    expe_to_run: Experiments to run.  Can be set in the benchmark file.
    filters: If provided, parse only the experiment matching the filters. Eg: expe=expe1:expe2,something=true.

"""
    kwargs = dict(locals()) # capture the function arguments

    cli_args.setup_env_and_kwargs(kwargs)

    benchmark_file = kwargs["benchmark_file"]
    try: benchmark_yaml_file = cli_args.get_benchmark_yaml_file(benchmark_file)
    except (ValueError, FileNotFoundError) as e:
        logging.error(f"Failed to parse the benchmark file: {e}")
        raise SystemExit(1)

    cli_args.update_kwargs_with_benchmark_file(kwargs, benchmark_yaml_file)

    cli_args.check_mandatory_kwargs(kwargs, ("workload", "results_dirname", "expe_to_run"))

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="benchmark")

        # ---

        workload_store = store.load_workload_store(kwargs)

        # ---

        dry = not run

        logging.info(f"Loading previous results ... ")
        workload_store.parse_data()
        logging.info(f"Loading previous results: done, found {len(common.Matrix.processed_map)} results")

        if dry:
            logging.info("#")
            logging.info("# DRY RUN")
            logging.info("#")

        script_to_run = matrix.Matrix(benchmark_yaml_file)
        script_to_run.run()

        return 0

    return cli_args.TaskRunner(run)
