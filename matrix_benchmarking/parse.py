import os, sys
import logging

import matrix_benchmarking.store as store
import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args

def main(workload: str = "",
          results_dirname: str = "",
          work_dir: str = "",
          filters: list[str] = [],
          clean: bool = False,
          run: bool = False,
          ):
    """
Run MatrixBenchmarking results parsing.

Run MatrixBenchmarking results parsing (for troubleshooting).

Env:
    MATBENCH_WORKLOAD
    MATBENCH_RESULTS_DIRNAME
    MATBENCH_WORK_DIR
    MATBENCH_FILTERS
    MATBENCH_CLEAN
    MATBENCH_RUN

See the `FLAGS` section for the descriptions.

Args:
    workload_dir: Name of the workload to execute. (Mandatory.)
    results_dirname: Name of the directory where the results will be stored. Can be set in the benchmark file. (Mandatory.)
    work_dir: Absolute path indicating where files should read/written.
    filters: If provided, parse only the experiment matching the filters. Eg: expe=expe1:expe2,something=true.
    clean: If 'True', run in cleanup mode.
    run: In cleanup mode: if 'False', list the results that would be cleanup. If 'True', execute the cleanup.
"""

    kwargs = dict(locals()) # capture the function arguments

    cli_args.setup_env_and_kwargs(kwargs)

    cli_args.check_mandatory_kwargs(kwargs, ("workload", "results_dirname",))

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="parse_clean")

        if kwargs["clean"]:
            logging.info("Running the result directory cleaner...")

        workload_store = store.load_workload_store(kwargs)

        logging.info(f"Loading results ... ")
        workload_store.parse_data()
        logging.info(f"Loading results: done, found {len(common.Matrix.processed_map)} results")

        if kwargs["clean"]:
            if not kwargs["run"]:
                logging.info("Cleaner ran in dry mode. Pass --run to perform the deletion.")

        return 0

    return cli_args.TaskRunner(run)
