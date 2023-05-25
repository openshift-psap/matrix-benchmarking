from .upload_lts import login

import logging
import requests
import json
import os
import pathlib

import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.store as store

def main(
        results_dirname: str = "",
        filters: str = "",
    ):
    """
Download MatrixBenchmark result from Horreum

Download MatrixBenchmark from Long-Term Storage, expects Horreum credentials/configuration to be available either in the enviornment or in an env file.

    results_dirname: The directory to place the downloaded results files. (Mandatory)
    filters: If provided, only download the experiments matching the filters. Eg: expe=expe1:expe2,something=true. (Optional.)
    """
    kwargs = {
        "horreum_url": None,
        "keycloak_url": None,
        "horreum_test": None,
        "horreum_uname": None,
        "horreum_passwd": None,
        **dict(locals())
    }

    cli_args.setup_env_and_kwargs(kwargs)
    cli_args.check_mandatory_kwargs(kwargs,
        ("results_dirname", "horreum_url", "horreum_url", "keycloak_url", "horreum_test", "horreum_uname", "horreum_passwd"),
        sensitive = ["horreum_url", "keycloak_url", "horreum_test", "horreum_uname", "horreum_passwd"]
    )

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="upload-lts")

        token = login(kwargs.get("keycloak_url"), kwargs.get('horreum_uname'), kwargs.get("horreum_passwd"))
        horreum_url = kwargs.get('horreum_url')
        test_id = get_test_id(horreum_url, kwargs.get('horreum_test'), token)

        download(kwargs.get('horreum_url'), test_id, token, filters, kwargs.get('results_dirname'))
    
    return cli_args.TaskRunner(run)


def download(url: str, id: int, token: str, filters: list[str], dest_dir: str):
    dataset_query = f"{url}/api/dataset/list/{id}"
    headers = {"Authorization": f"Bearer {token}"}
    if len(filters) > 0:
        filter_str = json.dumps(construct_filter_json(filters))
        logging.debug(filter_str)
        dataset_query = f"{dataset_query}?filter={requests.utils.quote(filter_str)}"
    datasets_req = requests.get(dataset_query, headers=headers, verify=False)

    if datasets_req.status_code != 200:
        raise RuntimeError(f"Could not retrieve datasets: {datasets_req.status_code} {datasets_req.content}")
    
    matching_runs = []
    for dataset in datasets_req.json()['datasets']:
        run = dataset['runId']
        if run not in matching_runs:
            matching_runs.append(dataset['runId'])

    logging.info(f"Found {len(matching_runs)} matching runs")

    for run in matching_runs:
        req = requests.get(f"{url}/api/run/{run}/data", verify=False)
        data = req.json()

        dirname = f"{dest_dir}/expe/from_lts/{run}"
        pathlib.Path(dirname).mkdir(exist_ok=True, parents=True)
        
        with open(f"{dirname}/data.json", 'w') as f:
            json.dump(data, f)

        write_settings(f"{dirname}/settings", data)
        with open(f"{dirname}/lts", "w") as f:
            f.write(' ')


def write_settings(fname, data):
    with open(fname, "w") as settings:
        for (key, val) in data['metadata']['settings'].items():
            settings.write(f"{key}={val}\n")


def get_test_id(url: str, name: str, token: str) -> int:
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    req = requests.get(f'{url}/api/test/byName/{name}', headers=headers, verify=False)
    if req.status_code != 200:
        raise RuntimeError(f"Could not get test id for {name}: {req.status_code} {req.content}")

    return req.json()["id"]


def construct_filter_json(filters: list[str]) -> dict:
    output = {}
    for kv in filters.split(','):
        key, found, value = kv.partition("=")
        try:
            value = int(value)
        except ValueError:
            pass
        try:
            value = float(value)
        except ValueError:
            pass
        output[key] = value
    return output
