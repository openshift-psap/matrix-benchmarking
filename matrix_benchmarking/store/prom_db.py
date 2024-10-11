#! /usr/bin/env python3

import tarfile
import logging
import tempfile
import shutil
import subprocess
import pathlib
import json
import types
import sys
import time
import os
import datetime
import typing

PROMETHEUS_URL = "http://localhost:9090"

def _parse_metric_values_from_file(metric_file):
    with open(metric_file) as f:
        json_metrics = json.load(f)

    import matrix_benchmarking.models # import here, otherwise this file cannot be executed standalone
    import pydantic

    return pydantic.parse_obj_as(matrix_benchmarking.models.PrometheusValues, json_metrics)


def _extract_metrics_from_prometheus(tsdb_path, process_metrics):
    import prometheus_api_client # lazy loading ...

    metrics_values = {}
    logging.info("Checking Prometheus availability ...")

    # ensure that prometheus is available
    subprocess.run(["prometheus", "--help"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    failed = False
    try:
        prom_cfg = os.environ.get("PROMETHEUS_CONFIG_FILE", "/etc/prometheus/prometheus.yml")

        prom_cmd = ["prometheus",
                    "--storage.tsdb.path", str(tsdb_path),
                    "--config.file", prom_cfg]

        prom_proc = subprocess.Popen(prom_cmd,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)

        logging.info("Waiting for Prometheus to respond to its API ...")
        RETRY_COUNT = 120 # 10 minutes
        time.sleep(5)
        for i in range(RETRY_COUNT):
            if prom_proc.poll() is not None:
                logging.error(f"Prometheus failed. Return code: {prom_proc.returncode}.")
                failed = True
                sys.exit(1)

            try:
                prom_connect = prometheus_api_client.PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True,)
                all_metrics = prom_connect.all_metrics()
                break
            except Exception:
                logging.info(f"Not available ... {i}/{RETRY_COUNT}")
        else:
            logging.error("Could not connect to Promtheus, aborting.")
            failed = True
            sys.exit(1)

        process_metrics(prom_connect)

        print("Reading ... done")
    finally:
        logging.info("Terminating Prometheus ...")
        prom_proc.terminate()
        prom_proc.kill()
        prom_proc.wait()
        if failed or prom_proc.returncode:
            logging.info("<Promtheus stderr>\n%s\n</Promtheus stderr>", prom_proc.stderr.read().decode("utf8").strip())


def prepare_prom_db(prometheus_tgz, process_metrics):
    logging.info(f"Processing {prometheus_tgz} ...")
    if not tarfile.is_tarfile(prometheus_tgz):
        logging.error(f"{prometheus_tgz} isn't a valid tar file.")
        return

    try:
        prom_db_tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="prometheus_db_"))
        with tarfile.open(prometheus_tgz, "r:gz") as prometheus_tarfile:
            prometheus_tarfile.extractall(prom_db_tmp_dir)

        _extract_metrics_from_prometheus(prom_db_tmp_dir, process_metrics)
    except EOFError as e:
        logging.error(f"File '{prometheus_tgz}' is an invalid tarball: %s", e)
    except KeyboardInterrupt:
        print("\n")
        logging.error("Interrupted :/")
        sys.exit(1)
    finally:
        shutil.rmtree(prom_db_tmp_dir, ignore_errors=True)


def extract_metrics(prometheus_tgz, metrics, dirname):
    metric_results = {}
    missing_metrics = []
    metrics_base_dir = dirname / "metrics"

    if not metrics: return

    with open(dirname / "metrics.txt", "w") as f:
        for metric in metrics:

            metric_name, metric_query = list(metric.items())[0] if isinstance(metric, dict) else (metric, metric)
            print(f"# {metric_name}", file=f)
            print(f"{metric_query}", file=f)

            metric_filename = metric_name.replace('.*', '').replace("'", "").replace("~", "")
            metric_file = metrics_base_dir / f"{metric_filename}.json"
            if not metric_file.exists():
                missing_metrics.append([metric_name, metric_query, metric_file])
                logging.info(f"No cache available for metric '{metric_name}'")
                continue

            metric_results[metric_name] = _parse_metric_values_from_file(metric_file)

    if not missing_metrics:
        logging.debug("All the metrics files exist, no need to launch Prometheus.")
        return metric_results

    metrics_base_dir.mkdir(exist_ok=True)

    metrics_values = {}
    def process_metrics(prom_connect):
        nonlocal metrics_values
        import prometheus_api_client.exceptions # lazy loading ...

        up_query = prom_connect.custom_query(query='up[60y]')
        if not up_query:
            logging.error(f"No 'up' metric available in the database at '{prometheus_tgz}'. Cannot proceed :/")
            return

        start_date = datetime.datetime.fromtimestamp(up_query[0]["values"][0][0])
        end_date = datetime.datetime.fromtimestamp(up_query[0]["values"][-1][0])
        del up_query # no need to keep it in memory

        duration = end_date - start_date
        SECOND_PER_STEP = 300
        MIN_STEP = 5
        step = max(MIN_STEP, int(duration.total_seconds() / SECOND_PER_STEP))
        logging.info(f"Prometheus up time is {duration}. Using a step value of {step}.")
        for metric_name, metric_query, metric_file in missing_metrics:
            if "(" in metric_query:
                try:
                    values = prom_connect.custom_query_range(query=metric_query, step=step,
                                                             start_time=start_date, end_time=end_date)
                except prometheus_api_client.exceptions.PrometheusApiClientException as e:
                    logging.warning(f"Fetching {metric_query} raised an exception")
                    logging.warning(f"Exception: {e}")
                    continue

                metrics_values[metric_name] = metric_values = []
                if not values: continue
                # deduplicate the values
                for current_values in values:
                    current_metric_values = {}
                    metric_values.append(current_metric_values)
                    current_metric_values["metric"] = current_values["metric"] # empty :/
                    current_metric_values["values"] = []
                    prev_val = None
                    prev_ts = None
                    has_skipped = False
                    for ts, val in current_values["values"]:
                        if val == prev_val:
                            has_skipped = True
                            prev_ts = ts
                            continue
                        if has_skipped:
                            current_metric_values["values"].append([prev_ts, prev_val])
                            has_skipped = False
                        current_metric_values["values"].append([ts, val])
                        prev_ts = ts
                        prev_val = val
                    if prev_val is not None and has_skipped:
                        # add the last value if the list wasn't empty
                        current_metric_values["values"].append([ts, val])

            else:
                metric_values = metrics_values[metric_name] = prom_connect.custom_query(query=f'{metric_query}[60y]')

            if not metric_values:
                logging.warning(f"{metric_name} has no data :/")

    logging.info("Launching Prometheus instance to grab %s", ", ".join([name for name, query, file in missing_metrics]))
    prepare_prom_db(prometheus_tgz, process_metrics)

    for metric_name, metric_query, metric_file in missing_metrics:
        with open(metric_file, "w") as f:
            json.dump(metrics_values.get(metric_name, []), f)

        logging.info(f"Metric {metric_name} fetched and stored.")
        metric_results[metric_name] = _parse_metric_values_from_file(metric_file)

    return metric_results


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"),
                    format="%(levelname)s | %(message)s",)

    def process_metrics(prom_connect):
        print("Prometheus is listing on", PROMETHEUS_URL)
        msg = input("Press enter to terminate it. (or type 'pdb' to enter pdb debugger) ")
        if msg == "pdb": import pdb;pdb.set_trace()
        pass

    prepare_prom_db(sys.argv[1], process_metrics)
