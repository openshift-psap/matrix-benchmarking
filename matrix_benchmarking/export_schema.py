import logging
import getpass
import datetime as dt
import requests
import json
import sys

import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.store as store

def main(workload: str = "", file: str = "-"):
    """
Export a JSON Schema for a particular workload

Export a JSON Schema for a workload, which is commonly used in Horreum

Args:
    workload: Name of the workload to execute. (Mandatory)
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

        output.write(store.get_custom_schema().schema_json(indent=4))
        output.close()
   
    return cli_args.TaskRunner(run)
