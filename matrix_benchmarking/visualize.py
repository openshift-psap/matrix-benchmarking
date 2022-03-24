import os, sys
import logging

import matrix_benchmarking.matrix
import matrix_benchmarking.store as store
import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args

def main(workload: str = "",
         results_dirname: str = "",
         work_dir: str = "",
         generate: bool = False):
    """
Visualize MatrixBenchmarking results.
Args:
    workload: Name of the workload to execute. (Mandatory.)
    results_dirname: Name of the directory where the results will be stored.  (Mandatory.)
    generate: If 'True', generates image files instead of running the Web UI.
    work_dir: Absolute path indicating where files should read/written.

Env:
    MATBENCH_WORKLOAD
    MATBENCH_RESULTS_DIRNAME
    MATBENCH_GENERATE
    MATBENCH_WORK_DIR

See the `FLAGS` section for the descriptions.
"""
    kwargs = dict(locals()) # capture the function arguments

    # lazy loading, to avoid importing these modules when not running in visualization mode

    import matrix_benchmarking.plotting.table_stats as table_stats
    import matrix_benchmarking.plotting.ui as ui
    import matrix_benchmarking.plotting.ui.web as ui_web

    cli_args.goto_work_directory(kwargs)
    cli_args.update_env_with_env_files()
    cli_args.update_kwargs_with_env(kwargs)

    cli_args.check_mandatory_kwargs(kwargs, ("workload", "results_dirname"))

    cli_args.store_kwargs(kwargs, execution_mode="visualize")

    # ---

    workload_store = store.load_workload_store(kwargs)

    # ---
    results_dirname = kwargs["results_dirname"]

    logging.info(f"Loading results from {results_dirname} ... ")
    workload_store.parse_data(results_dirname)
    logging.info(f"Loading results from {results_dirname} ... done. Found {len(common.Matrix.processed_map)} results.")

    try:
        ui.configure(kwargs)
    except Exception as e:
        logging.error(f"Failed to configure the plotting module: {e}")
        raise e

    table_stats.register_all()

    ui_web.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
