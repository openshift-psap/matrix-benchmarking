import logging
import getpass
import datetime as dt
import requests
import json
import sys
import contextlib
import datetime
import pathlib
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

        schema_dict = schema.schema()

        filename = kwargs.get("file")

        with smart_open(filename) as f:
            json.dump(schema_dict, f, indent=4)
            print("", file=f) # add EOL at EOF

        if filename != "-":
            filepath = pathlib.Path(filename)
            with smart_open(filepath.parent / "opensearch_mapping.json") as f:
                json.dump(create_opensearch_mapping(schema_dict), f, indent=4)
                print("", file=f) # add EOL at EOF

    return cli_args.TaskRunner(run)


TYPE_MAP = dict(
    string="text",
    number="float",
    integer="long",
    array="text",
)

FORMAT_TYPE_MAP = {
    "date-time": "date",
}

def create_opensearch_mapping(json_schema):
    definitions = {}

    os_mapping = {}
    def process(path, entry, dest):
        if defs := entry.get("definitions"):
            for def_name, def_value in defs.items():
                definitions[f"{path}/definitions/{def_name}"] = def_value

                if def_name == "PrometheusValue":
                    def_value["properties"]["values"]["index"] = False
                    def_value["properties"]["values"]["type"] = "text"

        if ref := entry.get("$ref"):
            entry.pop("$ref")
            entry |= definitions[ref].copy()

        if ref := entry.get("items", {}).get("$ref"):
            entry.pop("items")
            entry |= definitions[ref].copy()

        if path == "#" and "type" in entry:
            entry.pop("type")

        if path.endswith("values"):
            dest["index"] = False
            entry["type"] = "text"

        if path != "#" and "title" in entry and not "type" in entry:
            entry["type"] = "object"
            entry["index"] = False

        for k, v in entry.items():
            if k == "$ref":
                logging.fatal("Found a stray $ref :/")
                sys.exit(1)
            elif k == "type":
                if fmt := entry.get("format"):
                    v = FORMAT_TYPE_MAP.get(fmt, v)

                dest[k] = TYPE_MAP.get(v, v) # convert or passthrough
            elif k in (
                    "additionalProperties", "title", "format", "default", "required", "pattern", "value", # ignore, not supported
                    "description", "enum",

                    "items", "definitions", # ignore, already processed
            ):
                continue # ignore
            elif isinstance(v, dict):
                processed_dict = {}
                if k == "regression_results":
                    return
                process(f"{path}/{k}", v, processed_dict)
                dest[k] = processed_dict
            else:
                dest[k] = v

    process("#", json_schema, os_mapping)

    return os_mapping
