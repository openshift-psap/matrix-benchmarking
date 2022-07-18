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

import prometheus_api_client

PROMETHEUS_URL = "http://localhost:9090"

def _parse_metric_values_from_file(metric_file):
    with open(metric_file) as f:
        json_metrics = json.load(f)

    return json_metrics


def _extract_metrics_from_prometheus(tsdb_path, process_metrics):
    metrics_values = {}
    logging.info("Checking Prometheus availability ...")

    # ensure that prometheus is available
    subprocess.run(["prometheus", "--help"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    failed = False
    try:
        prom_proc = subprocess.Popen(["prometheus", "--storage.tsdb.path", str(tsdb_path)],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)

        logging.info("Waiting for Prometheus to respond to its API ...")
        RETRY_COUNT = 10
        time.sleep(5)
        for i in range(RETRY_COUNT):
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
        if failed:
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


def extract_metrics(prometheus_tgz, metrics, dirname, filename_prefix=""):
    metric_results = {}
    missing_metrics = []
    for metric in metrics:
        metric_file = dirname / "metrics" / f"{filename_prefix}{metric}.json"
        if not metric_file.exists():
            missing_metrics.append(metric)
            logging.info(f"{metric_file} missing")
            continue

        metric_results[metric] = _parse_metric_values_from_file(metric_file)

    if not missing_metrics:
        logging.debug("All the metrics files exist, no need to launch Prometheus.")
        return metric_results

    metrics_values = {}
    def process_metrics(prom_connect):
        nonlocal metrics_values
        for metric in missing_metrics:
            metrics = metrics_values[metric] = prom_connect.custom_query(query=f'{metric}[60y]')
            if not metrics:
                logging.warning(f"{filename_prefix}{metric} has no data :/")

    logging.info("Launching Prometheus instance to grab %s", ", ".join(missing_metrics))
    prepare_prom_db(prometheus_tgz, process_metrics)

    for metric in missing_metrics:
        if metric not in metrics_values or not metrics_values[metric]:
            logging.warning(f"{metric} not found in Promtheus database.")

        metric_file = dirname / "metrics" / f"{filename_prefix}{metric}.json"

        with open(metric_file, "w") as f:
            json.dump(metrics_values.get(metric, {}), f)

        logging.info(f"{metric_file} generated")
        metric_results[metric] = _parse_metric_values_from_file(metric_file)

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
