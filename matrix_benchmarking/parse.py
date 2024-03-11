import os, sys
import logging
import json
import functools

import matrix_benchmarking.store as store
import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args

def json_dumper(obj, strict=False):
    import datetime
    import pathlib

    if isinstance(obj, dict):
        return obj

    elif hasattr(obj, "toJSON"):
        return obj.toJSON()

    elif hasattr(obj, "json"):
        return obj.dict(by_alias=True)

    elif hasattr(obj, "__dict__"):
        return obj.__dict__

    if isinstance(obj, datetime.datetime):
        return obj.isoformat()

    elif isinstance(obj, pathlib.Path):
        return str(obj)
    elif not strict:
        return str(obj)
    else:
        raise RuntimeError(f"No default serializer for object of type {obj.__class__}: {obj}")


def main(workload: str = "",
         workload_base_dir: str = "",
         results_dirname: str = "",
         filters: list[str] = [],
         clean: bool = False,
         run: bool = False,
         output_lts: str = "",
         output_matrix: str = "",
         pretty: bool = True,
         lts: bool = False,
         ):
    """
Run MatrixBenchmarking results parsing.

Run MatrixBenchmarking results parsing (for troubleshooting).

Env:
    MATBENCH_WORKLOAD
    MATBENCH_WORKLOAD_BASE_DIR
    MATBENCH_RESULTS_DIRNAME
    MATBENCH_FILTERS
    MATBENCH_CLEAN
    MATBENCH_RUN

See the `FLAGS` section for the descriptions.

Args:
    workload: Name of the workload to execute. (Mandatory.)
    workload_base_directory: the directory from where the workload packages should be loaded. (Optional)
    results_dirname: Name of the directory where the results will be stored. Can be set in the benchmark file. (Mandatory.)
    filters: If provided, parse only the experiment matching the filters. Eg: expe=expe1:expe2,something=true.
    clean: If 'True', run in cleanup mode.
    run: In cleanup mode: if 'False', list the results that would be cleanup. If 'True', execute the cleanup.
    output_lts: Output the parsed LTS results into a specified file, or to stdout if '-' is supplied
    output_matrix: Output the internal entry matrix into a specified file, or to stdout if '-' is supplied
    lts: If 'True', invoke the LTS parser only.
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

        if kwargs.get("lts"):
            workload_store.parse_lts_data()
        else:
            workload_store.parse_data()

        logging.info(f"Loading results: done, found {len(common.Matrix.processed_map)} results")

        if kwargs["clean"]:
            if not kwargs["run"]:
                logging.info("Cleaner ran in dry mode. Pass --run to perform the deletion.")

        common.Matrix.print_settings_to_log()

        if kwargs["output_matrix"]:
            indent = None
            if kwargs['pretty']:
                indent = 4

            parsed_results = []
            for entry in common.Matrix.processed_map.values():
                parsed_results.append(entry)

            file = None
            try:
                file = sys.stdout if kwargs["output_matrix"] == '-' else open(kwargs["output_matrix"], "w")
                json.dump(parsed_results, file, indent=indent, default=functools.partial(json_dumper, strict=False))
                print("", file=file) # add the EOL delimiter after the JSON dump
            finally:
                if file:
                    file.close()

        if kwargs["output_lts"]:
            indent = None
            if kwargs['pretty']:
                indent = 4

            parsed_results = []
            for payload, _, __ in workload_store.build_lts_payloads():
                parsed_results.append(payload)

            file = None
            try:
                file = sys.stdout if kwargs["output_lts"] == '-' else open(kwargs["output_lts"], "w")
                json.dump(parsed_results, file, indent=indent, default=functools.partial(json_dumper, strict=False))
                print("", file=file)
            finally:
                if file:
                    file.close()

        has_result = len(common.Matrix.processed_map) != 0
        return 0 if has_result else 1

    return cli_args.TaskRunner(run)
