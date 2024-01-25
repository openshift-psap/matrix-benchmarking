import logging
import getpass
import datetime as dt
import requests
import json
import sys
import contextlib
import datetime
from typing import List, Union, Any, Optional

from pydantic import BaseModel

import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.store as store


@contextlib.contextmanager
def smart_open(filename=None):
    if filename and filename != '-':
        fh = open(filename, 'w')
    else:
        fh = sys.stdout

    try:
        yield fh
    finally:
        if fh is not sys.stdout:
            fh.close()


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

        schema = store.get_lts_schema()
        if not schema:
            logging.error(f"No LTS schema registered for workload '{workload}', cannot export it.")
            sys.exit(1)

        schema_dict = create_opensearch_mapping(schema.schema())

        with smart_open(file) as f:
            json.dump(schema_dict, f, indent=4)
            print("", file=f) # add EOL at EOF

    return cli_args.TaskRunner(run)
