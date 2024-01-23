import logging
import requests
import json
import os
import pathlib
import datetime
import yaml
import importlib
import sys

from opensearchpy import OpenSearch

import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.store as store

LTS_ANCHOR_NAME = "source.lts.yaml"

def main(workload: str = "",
         workload_base_dir: str = "",
         results_dirname: str = "",
         lts_results_dirname: str = "",
         filters: list[str] = [],
         ):
    """
Analyze MatrixBenchmark LTS results

Analyze MatrixBenchmarking LTS results to detect performance regression

Env:
    MATBENCH_WORKLOAD
    MATBENCH_WORKLOAD_BASE_DIR
    MATBENCH_RESULTS_DIRNAME
    MATBENCH_FILTERS

Args:
    workload: Name of the workload to execute. (Mandatory.)
    workload_base_directory: the directory from where the workload packages should be loaded. (Optional)
    results_dirname: Name of the directory where the results are stored. (Mandatory.)
    lts_results_dirname: Name of the directory where the LTS results are stored. (Mandatory.)
    filters: If provided, analyze only the experiment matching the filters. Eg: expe=expe1:expe2,something=true.

    """
    kwargs = dict(locals()) # capture the function arguments

    cli_args.setup_env_and_kwargs(kwargs)
    cli_args.check_mandatory_kwargs(kwargs, ("workload", "results_dirname", "lts_results_dirname"))

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="analyze-lts")

        workload_store = store.load_workload_store(kwargs)

        logging.info(f"Loading results ... ")

        workload_store.parse_data()
        common.Matrix.print_settings_to_log()
        logging.info(f"Loading results ... done. Found {len(common.Matrix.processed_map)} results.")
        logging.info("")
        logging.info("--- LTS --- ")

        workload_store.parse_lts_data()

        common.LTS_Matrix.print_settings_to_log()
        logging.info(f"Loading LTS results ... done. Found {len(common.LTS_Matrix.processed_map)} results.")

        if not common.Matrix.processed_map:
            logging.error("Not result found, exiting.")
            return 1

        workload_analyze = get_workload_analyze_module(workload_store)

        number_of_failures = workload_analyze.run()

        logging.info(f"Analyses found {number_of_failures} issue{'s' if number_of_failures > 1 else ''}.")

        return number_of_failures


    return cli_args.TaskRunner(run)


def get_workload_analyze_module(workload_store):
    workload_package = workload_store.__package__.removesuffix(".store")
    module = f"{workload_package}.analyze"
    logging.info(f"Loading {module} module ...")

    try:
        analyze_module = importlib.import_module(module)
    except ModuleNotFoundError:
        logging.critical(f"Module {module} does not exist :/")
        sys.exit(1)

    logging.info(f"Loading {module} module ... done.")

    return analyze_module
