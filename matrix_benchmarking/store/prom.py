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

import prometheus_api_client

def _parse_metric_values_from_file(metric_file):
    with open(metric_file) as f:
        json_metrics = json.load(f)

    return json_metrics


def _extract_metrics_from_prometheus(tsdb_path, missing_metrics, destdir):
    metrics_values = {}
    logging.info("Launching Prometheus instance to grab %s", ", ".join(missing_metrics))

    # ensure that prometheus is available
    subprocess.run(["prometheus", "--help"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    failed = False
    try:
        prom_proc = subprocess.Popen(["prometheus", "--storage.tsdb.path", str(tsdb_path)],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)

        logging.info("Waiting for Prometheus to respond to its API ...")
        RETRY_COUNT = 5
        time.sleep(5)
        for i in range(RETRY_COUNT):
            try:
                prom_connect = prometheus_api_client.PrometheusConnect(url=f"http://localhost:9090", disable_ssl=True,)
                all_metrics = prom_connect.all_metrics()
                break
            except Exception:
                logging.info(f"Not available ... {i}/{RETRY_COUNT}")
        else:
            logging.error("Could not connect to Promtheus, aborting.")
            failed = True
            sys.exit(1)

        for metric in missing_metrics:
            metrics_values[metric] = prom_connect.custom_query(query=f'{{__name__="{metric}"}}[60y]')

        print("Reading ... done")
    finally:
        logging.info("Terminating Prometheus ...")
        prom_proc.terminate()
        prom_proc.kill()
        prom_proc.wait()
        if failed:
            logging.info("<Promtheus stderr>\n%s\n</Promtheus stderr>", prom_proc.stderr.read().decode("utf8").strip())

    return metrics_values

def extract_metrics(prometheus_tgz, metrics, dirname):

    metric_results = {}
    missing_metrics = []
    for metric in metrics:
        metric_file = dirname / f"{metric}.json"
        if not metric_file.exists():
            missing_metrics.append(metric)
            logging.info(f"{metric_file} missing")
            continue

        metric_results[metric] = _parse_metric_values_from_file(metric_file)

    if not missing_metrics:
        logging.debug("All the metrics files exist, no need to launch Prometheus.")
        return metric_results
    logging.info("Missing metrics in %s", dirname)

    if not tarfile.is_tarfile(prometheus_tgz):
        logging.error("{prometheus_tgz} isn't a valid tar file.")
        return None

    try:
        prom_db_tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="prometheus_db_"))
        with tarfile.open(prometheus_tgz, "r:gz") as prometheus_tarfile:
            prometheus_tarfile.extractall(prom_db_tmp_dir)

        metrics_values = _extract_metrics_from_prometheus(prom_db_tmp_dir / "prometheus", missing_metrics, dirname)
    except KeyboardInterrupt:
        print("\n")
        logging.error("Interrupted :/")
        sys.exit(1)
    finally:
        shutil.rmtree(prom_db_tmp_dir, ignore_errors=True)

    for metric in missing_metrics:
        if metric not in metrics_values or not metrics_values[metric]:
            logging.warning(f"{metric} not found in Promtheus database.")

        metric_file = dirname / f"{metric}.json"

        with open(metric_file, "w") as f:
            json.dump(metrics_values[metric], f)

        logging.info(f"{metric_file} generated")
        metric_results[metric] = _parse_metric_values_from_file(metric_file)

    return metric_results
