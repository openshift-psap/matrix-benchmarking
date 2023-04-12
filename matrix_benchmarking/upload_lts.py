import logging
import getpass
import datetime as dt
import requests
import json

import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.store as store

def main(
        workload: str = "",
        results_dirname: str = "",
        filters: list[str] = [],
        dry_run: bool = False
    ):
    """
Upload MatrixBenchmark result to Horreum

Upload MatrixBenchmark to Long-Term Storage

Args:
    workload: Name of the workload to execute. (Mandatory)
    results_dirname: Name of the directory where the results are stored. Can be set in the benchmark file. (Mandatory)
    horreum_url: The URL to the Horreum instance where the data will be uploaded. (Mandatory)
    keycloak_url: The URL for the KeyCloak instance used to login to Horruem. (Mandatory)
    horreum_test: The name of the test in Horreum for the data to be uploaded under. (Mandatory)
    horreum_uname: The username of your Horreum user. (Mandatory)
    horreum_passwd: The password for your Horreum user. (Mandatory)

    filters: If provided, parse and upload only the experiment matching the filters. Eg: expe=expe1:expe2,something=true. (Optional.)
    dry_run: If provided, only parse results and not upload results to horreum. (Optional.)
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
        ("workload", "results_dirname", "horreum_url", "keycloak_url", "horreum_test", "horreum_uname", "horreum_passwd"), 
        sensitive=["horreum_url", "keycloak_url", "horreum_test", "horreum_uname", "horreum_passwd"]
    )

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="upload-lts")
        workload_store = store.load_workload_store(kwargs)
        workload_store.parse_data()

        if not dry_run:
            token = login(kwargs.get('keycloak_url'), kwargs.get("horreum_uname"), kwargs.get("horreum_passwd"))

        for (payload, start, end) in workload_store.build_lts_payloads():
            logging.debug(f"Sending {json.dumps(payload)} to Horreum")
            if not dry_run:
                upload(kwargs.get('horreum_url'), payload, kwargs.get('horreum_test'), start, end, token)
    
    return cli_args.TaskRunner(run)


def upload(url: str, payload: dict, test: str, starttime: dt.datetime, endtime: dt.datetime, token: str):
    start = int(dt.datetime.timestamp(starttime) * 1e3)
    end = int(dt.datetime.timestamp(endtime) * 1e3)
    resp = requests.post(
        f"{url}/api/run/data?test={test}&start={start}&stop={end}&access=PUBLIC",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        verify=False
    )
    print(resp.content)


def login(url: str, uname: str, passwd: str) -> str:
    from keycloak import KeycloakOpenID
    open_id = KeycloakOpenID(
        server_url=url,
        realm_name="horreum",
        client_id="horreum-ui",
        verify=False
    )
    return open_id.token(uname, passwd)['access_token']
