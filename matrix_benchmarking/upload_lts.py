import logging
import getpass
import datetime as dt
import requests
import json
import functools

import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.store as store
import matrix_benchmarking.download_lts as download_lts
import matrix_benchmarking.generate_lts_schema as generate_lts_schema
import matrix_benchmarking.parse as parse


def main(
        workload: str = "",
        workload_base_dir: str = "",
        results_dirname: str = "",
        opensearch_host: str = "",
        opensearch_port: str = "",
        opensearch_username: str = "",
        opensearch_password: str = "",
        opensearch_index: str = "",
        filters: list[str] = [],
        dry_run: bool = False,
    ):
    """
Upload MatrixBenchmark LTS payloads to OpenSearch

Upload MatrixBenchmark LTS payloads to OpenSearch, expects OpenSearch credentials and configuration to be available either in the enviornment or in an env file.

Args:
    workload: name of the workload to execute. (Mandatory)
    workload_base_dir: the directory from where the workload packages should be loaded. (Optional)

    results_dirname: name of the directory where the results are stored. Can be set in the benchmark file. (Mandatory)

    opensearch_host: hostname of the OpenSearch instance
    opensearch_port: port of the OpenSearch instance
    opensearch_username: username of the OpenSearch instance
    opensearch_password: password of the OpenSearch instance
    opensearch_index: the OpenSearch index where the LTS payloads are stored (Mandatory)

    filters: If provided, parse and upload only the experiment matching the filters. Eg: expe=expe1:expe2,something=true. (Optional.)
    dry_run: If provided, only parse results and not upload results to horreum. (Optional.)
    """

    kwargs = dict(locals()) # capture the function arguments

    optionals_flags = ["filters", "workload_base_dir", "dry_run"]
    safe_flags = ["results_dirname", "workload", "opensearch_index"] + optionals_flags

    cli_args.setup_env_and_kwargs(kwargs)
    cli_args.check_mandatory_kwargs(kwargs,
                                    mandatory_flags=[k for k in kwargs.keys() if k not in optionals_flags],
                                    sensitive_flags=[k for k in kwargs.keys() if k not in safe_flags])

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="upload-lts")

        workload_store = store.load_workload_store(kwargs)

        if kwargs.get("dry_run"):
            logging.warning("Running in dry mode.")

        logging.info(f"Loading results ... ")
        workload_store.parse_data()
        logging.info(f"Loading results: done, found {len(common.Matrix.processed_map)} results")

        common.Matrix.print_settings_to_log()

        client = download_lts.connect_opensearch_client(kwargs) \
            if not kwargs.get("dry_run") else None

        logging.info(f"Uploading to OpenSearch /{kwargs.get('opensearch_index')}...")

        return upload(client, workload_store, kwargs.get("dry_run"), kwargs.get("opensearch_index"))

    return cli_args.TaskRunner(run)


def opensearch_create_index(client, dry_run, opensearch_index):
    if dry_run:
        logging.info(f"Check if index '{opensearch_index}' exists or create it. (dry run)")
        return

    index_body = {
        'settings': {
            'index': {
                'number_of_shards': 4
            },
            'mapping': {
                'total_fields': {
                    "limit": 2000,
                },
            },
        },
    }

    # Check if the index already exists
    if client.indices.exists(index=opensearch_index):
        del index_body["settings"]["index"]["number_of_shards"] # Can't update non dynamic settings [[index.number_of_shards]] for open indices
        client.indices.put_settings(index=opensearch_index, body=index_body)

        logging.info(f"Index '{opensearch_index}' updated.")
        return


    # create the index
    client.indices.create(index=opensearch_index, body=index_body)
    logging.info(f"Index '{opensearch_index}' created.")


def update_mapping(client, workload_store, dry_run, opensearch_index):
    schema = store.get_lts_schema()
    mapping = generate_lts_schema.create_opensearch_mapping(schema.schema())

    import pdb;pdb.set_trace()
    pass


def get_kpi_index_name(opensearch_index, kpi_name):
    return f"{opensearch_index}.{kpi_name}"


def create_indexes(client, workload_store, dry_run, opensearch_index, lts_payloads):
    indexes_to_create = set()
    indexes_to_create.add(opensearch_index)

    for lts_payload, _, _ in lts_payloads:
        payload_json = json.dumps(lts_payload, default=functools.partial(parse.json_dumper, strict=False))
        payload_dict = json.loads(payload_json)

        for kpi_name, kpi in payload_dict.get("kpis", {}).items():
            kpi_index = get_kpi_index_name(opensearch_index, kpi_name)
            indexes_to_create.add(kpi_index)

    logging.info(f"Creating/updating {len(indexes_to_create)} indexes ...")
    for index_name in indexes_to_create:
        opensearch_create_index(client, dry_run, index_name)


def upload(client, workload_store, dry_run, opensearch_index):
    variables = [k for k, v in common.Matrix.settings.items() if len(v) > 1]

    lts_payloads = list(workload_store.build_lts_payloads())

    create_indexes(client, workload_store, dry_run, opensearch_index, lts_payloads)

    for idx, (payload, start, end) in enumerate(lts_payloads):
        try:
            settings_dict = parse.json_dumper(payload.metadata.settings, strict=False)
            key = ",".join(f"{k}={v}" for k, v in settings_dict.items() if (not variables or k in variables))
        except Exception as e:
            logging.warning(f"Failed to compute the name of the entry: {e}")
            key = str(payload.metadata.settings)

        logging.info(f"Uploading payload #{idx} | {key}")

        payload_json = json.dumps(payload, default=functools.partial(parse.json_dumper, strict=False))
        payload_dict = json.loads(payload_json)

        upload_kpis_to_opensearch(client, payload_dict, dry_run, opensearch_index)
        upload_lts_to_opensearch(client, payload_dict, dry_run, opensearch_index)
        upload_regression_results_to_opensearch(client, payload_dict, dry_run, opensearch_index)

    logging.info("All done :)")


def upload_lts_to_opensearch(client, payload_dict, dry_run, opensearch_index):
    logging.info(f"Uploading the LTS document to /{opensearch_index} ...")

    return upload_to_opensearch(client, payload_dict, payload_dict["metadata"]["test_uuid"], dry_run, opensearch_index)


def upload_kpis_to_opensearch(client, payload_dict, dry_run, opensearch_index):

    if "kpis" not in payload_dict.keys():
        logging.info(f"==> no KPI found in the payload.")
        return

    for kpi_name, kpi in payload_dict.get("kpis", {}).items():
        kpi_index = get_kpi_index_name(opensearch_index, kpi_name)
        logging.info(f"Uploading the KPI to /{kpi_index} ...")

        upload_to_opensearch(client, kpi, kpi["test_uuid"], dry_run, kpi_index)


def upload_regression_results_to_opensearch(client, payload_dict, dry_run, opensearch_index):
    if "regression_results" not in payload_dict.keys():
        logging.info(f"==> no regression results found in the payload.")
        return

    logging.info(f"Uploading regression results to opensearch ... (stub)")
    for idx, regression_result in enumerate(payload_dict["regression_results"]):
        regression_result_index = f"{opensearch_index}__regression_results_{idx}"
        opensearch_create_index(client, True, regression_result_index)

        logging.info(regression_result)
        upload_to_opensearch(client, regression_result, payload_dict["metadata"]["test_uuid"], True, regression_result_index)


def upload_to_opensearch(client, document, document_id, dry_run, index):
    if dry_run:
        logging.info(f"==> skip upload (dry run)")
        return

    response = client.index(
        index=index,
        body=document,
        refresh=True,
        id=document_id,
    )

    logging.info(f"==> {response['result']}")
