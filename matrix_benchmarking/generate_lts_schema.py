import logging
import getpass
import datetime as dt
import requests
import json
import sys

import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.store as store

def main(workload: str = "",
         workload_base_dir: str = "",
         file: str = "-"):
    """
Generate the JSON LTS schema of the workload

Generate the JSON LTS schema of the workload

Args:
    workload: Name of the workload to execute. (Mandatory)
    workload_base_directory: the directory from where the workload packages should be loaded. (Optional)
    file: Name of the file to export the schema to, "-" to output to stdout.  (Default is "-")
"""

    kwargs = dict(locals())

    cli_args.setup_env_and_kwargs(kwargs)
    cli_args.check_mandatory_kwargs(kwargs, ["workload"])

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="export_schema")
        workload_store = store.load_workload_store(kwargs)

        if file == '-':
            output = sys.stdout
        else:
            output = open(file, 'w')

        schema = store.get_lts_schema()
        if not schema:
            logging.error(f"No LTS schema registered for workload '{workload}', cannot export it.")
            sys.exit(1)

        output.write(schema.schema_json(indent=4))
        output.close()

    return cli_args.TaskRunner(run)
