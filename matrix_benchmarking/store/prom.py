import tarfile
import logging
import tempfile
import shutil
import subprocess
import pathlib
from collections import defaultdict
import json
import types

def _parse_metric_values_from_file(metric_file):
    results = []
    with open(metric_file) as f:
        for line in f.readlines():
            str_labels, value, ts = line.strip().rsplit(maxsplit=2)
            json_line = (str_labels.replace("{", '{"')
                                   .replace("=", '":')
                                   .replace(", ", ', "'))
            try:
                json_labels = json.loads(json_line)
            except Exception: import pdb;pdb.set_trace()

            labels = types.SimpleNamespace()
            labels.__dict__.update(json_labels)
            labels.__value__ = value
            labels.__ts__ = int(ts)

            results.append(labels)

    return results


def _extract_metrics_from_tsdb(tsdb_path, missing_metrics, destdir):
    raw_metrics_values = defaultdict(list)
    tsdb_dump_proc = subprocess.Popen(["tsdb", "dump", str(tsdb_path)],
                                      stdout=subprocess.PIPE)
    logging.info("Reading promtheus database...")
    logging.info("Searching for metrics: %s", ", ".join(missing_metrics))
    for b_line in tsdb_dump_proc.stdout:
        line = b_line.decode("ascii")
        for metric in missing_metrics:
            if f'__name__="{metric}",' not in line: continue
            raw_metrics_values[metric].append(line.strip())
            break

    print("Reading ... done")

    if tsdb_dump_proc.wait() != 0:
        raise RuntimeError("Prometheus TSDB extraction failed.")

    return raw_metrics_values

def extract_metrics(prometheus_tgz, metrics, dirname):
    metric_results = {}
    missing_metrics = []
    for metric in metrics:
        metric_file = dirname / f"{metric}.prom"
        if not metric_file.exists():
            missing_metrics.append(metric)
            logging.info(f"{metric_file} missing")
            continue

        metric_results[metric] = _parse_metric_values_from_file(metric_file)

    if not missing_metrics:
        logging.debug("All the metrics files exist, no need to launch Prometheus.")
        return metric_results


    if not tarfile.is_tarfile(prometheus_tgz):
        logging.error("{prometheus_tgz} isn't a valid tar file.")
        return None

    try:
        prom_db_tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="prometheus_db_"))
        with tarfile.open(prometheus_tgz, "r:gz") as prometheus_tarfile:
            prometheus_tarfile.extractall(prom_db_tmp_dir)

        raw_metrics_values = _extract_metrics_from_tsdb(prom_db_tmp_dir / "prometheus", missing_metrics, dirname)
    except KeyboardInterrupt:
        print("\n")
        logging.error("Interrupted :/")
        sys.exit(1)
    finally:
        shutil.rmtree(prom_db_tmp_dir, ignore_errors=True)

    for metric in missing_metrics:
        if metric not in raw_metrics_values or not raw_metrics_values[metric]:
            logging.warning(f"{metric} not found in Promtheus database.")

        metric_file = dirname / f"{metric}.prom"
        with open(metric_file, "w") as f:
            for line in raw_metrics_values[metric]:
                print(line, file=f)
        logging.info(f"{metric_file} generated")
        metric_results[metric] = _parse_metric_values_from_file(metric_file)

    return metric_results
