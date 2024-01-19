import logging
import requests
import json
import os
import pathlib
import datetime
import yaml

from opensearchpy import OpenSearch

import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.store as store

LTS_ANCHOR_NAME = "source.lts.yaml"

def main(opensearch_host: str = "",
         opensearch_port: str = "",
         opensearch_username: str = "",
         opensearch_password: str = "",
         opensearch_index: str = "",
         results_dirname: str = "",
         filters: list[str] = [],
         ):
    """
Download MatrixBenchmark result from OpenSearch

Download MatrixBenchmark from Long-Term Storage, expects OpenSearch credentials and configuration to be available either in the enviornment or in an env file.

    opensearch_host: hostname of the OpenSearch instance
    opensearch_port: port of the OpenSearch instance
    opensearch_username: username of the OpenSearch instance
    opensearch_password: password of the OpenSearch instance
    opensearch_index: the OpenSearch index where the LTS payloads are stored (Mandatory)

    results_dirname: The directory to place the downloaded results files.
    filters: If provided, only download the experiments matching the filters. Eg: expe=expe1:expe2,something=true. (Optional.)
    """
    kwargs = dict(locals()) # capture the function arguments
    optionals_flags = ["filters"]
    safe_flags = ["filters", "results_dirname", "opensearch_index"]

    cli_args.update_env_with_env_files()
    cli_args.update_kwargs_with_env(kwargs)
    cli_args.check_mandatory_kwargs(kwargs,
                                    mandatory_flags=[k for k in kwargs.keys() if k not in optionals_flags],
                                    sensitive_flags=[k for k in kwargs.keys() if k not in safe_flags])

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="download-lts")

        client = connect_opensearch_client(kwargs)

        return download(
            client,
            kwargs.get("opensearch_index"),
            kwargs.get("filters"),
            pathlib.Path(kwargs.get("results_dirname")),
            kwargs.get("max_records")
        )

    return cli_args.TaskRunner(run)


def connect_opensearch_client(kwargs):
    auth = (kwargs["opensearch_username"], kwargs["opensearch_password"])

    client = OpenSearch(
        hosts=[{'host': kwargs["opensearch_host"], 'port': kwargs["opensearch_port"]}],
        timeout=60,
        http_compress=True,
        http_auth=auth,
        use_ssl=True,
        verify_certs=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )

    return client

def download(client, opensearch_index, filters, results_dirname, max_records):
    lts_dir_anchor = results_dirname / LTS_ANCHOR_NAME
    if lts_dir_anchor.exists():
        logging.critical(f"{lts_dir_anchor} already exists, cannot continue.")
        return 1

    logging.info(f"Querying OpenSearch {opensearch_index} ...")

    query = {
        "size": max_records
    }

    # Restrict the results to specific settings
    if filters:
        query["query"] = {
            "bool": {
                "must": [
                    {"match": {k: v}} for k, v in filters.items()
                ]
            }
        }

    search = client.search(
        body=query,
        index=opensearch_index
    )

    logging.info(f"Saving OpenSearch {opensearch_index} results ...")
    saved = 0

    with open(lts_dir_anchor, "w") as f:
        anchor = dict(
            index=opensearch_index,
            date=datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            filters=filters,
        )
        yaml.dump(anchor, f, indent=4)
        print("", file=f) # add EOL


    results_dirname.mkdir(exist_ok=True, parents=True)
    for hit in search["hits"]["hits"]:
        with open(results_dirname / f"{opensearch_index}_{hit['_id']}.json", "w") as f:
            entry = hit["_source"]
            json.dump(entry, f, indent=4)
            print("", file=f) # add EOL

        saved += 1

    logging.info(f"Saved {saved} OpenSearch {opensearch_index} results.")
