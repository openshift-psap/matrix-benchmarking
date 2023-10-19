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

    if hasattr(obj, "toJSON"):
        return obj.toJSON()

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
         results_dirname: str = "",
         filters: list[str] = [],
         clean: bool = False,
         run: bool = False,
         output_lts: str = "",
         output_matrix: str = "",
         pretty: bool = True
         ):
    """
Run MatrixBenchmarking results parsing.

Run MatrixBenchmarking results parsing (for troubleshooting).

Env:
    MATBENCH_WORKLOAD
    MATBENCH_RESULTS_DIRNAME
    MATBENCH_FILTERS
    MATBENCH_CLEAN
    MATBENCH_RUN

See the `FLAGS` section for the descriptions.

Args:
    workload: Name of the workload to execute. (Mandatory.)
    results_dirname: Name of the directory where the results will be stored. Can be set in the benchmark file. (Mandatory.)
    filters: If provided, parse only the experiment matching the filters. Eg: expe=expe1:expe2,something=true.
    clean: If 'True', run in cleanup mode.
    run: In cleanup mode: if 'False', list the results that would be cleanup. If 'True', execute the cleanup.
    output_lts: Output the parsed LTS results into a specified file, or to stdout if '-' is supplied
    output_matrix: Output the internal entry matrix into a specified file, or to stdout if '-' is supplied
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

        if common.Matrix.processed_map:
            logging.info("Settings matrix:")
        for key, values in common.Matrix.settings.items():
            if key == "stats": continue
            common.Matrix.settings[key] = sorted(values)
            logging.info(f"{key:20s}: {', '.join(map(str, common.Matrix.settings[key]))}")

        if kwargs["output_matrix"]:
            file = sys.stdout if kwargs["output_matrix"] == '-' else open(kwargs["output_matrix"], "w")
            indent = None
            if kwargs['pretty']:
                indent = 4

            parsed_results = []
            for entry in common.Matrix.processed_map.values():
                parsed_results.append(entry)

            json.dump(parsed_results, file, indent=indent, default=functools.partial(json_dumper, strict=False))
            print("", file=file)
            file.close()

        if kwargs["output_lts"]:
            file = sys.stdout if kwargs["output_lts"] == '-' else open(kwargs["output_lts"], "w")
            indent = None
            if kwargs['pretty']:
                indent = 4

            parsed_results = []
            for (payload, _, __) in workload_store.build_lts_payloads():
                parsed_results.append(payload)

            json.dump(parsed_results, file, indent=indent, default=functools.partial(json_dumper, strict=False))
            print("", file=file)
            file.close()

        has_result = len(common.Matrix.processed_map) != 0
        return 0 if has_result else 1

    return cli_args.TaskRunner(run)
