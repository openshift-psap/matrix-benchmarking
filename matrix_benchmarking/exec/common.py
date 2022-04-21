import logging
import sys
import yaml
import types
import datetime
import pathlib
import os

import jinja2

import matrix_benchmarking.exec.kube as kube
import matrix_benchmarking.exec.prom as prom

def apply_yaml_template(template_file, settings):
    with open(template_file) as f:
        template_str = f.read()

    template = jinja2.Template(template_str).render(settings)

    return template, list(yaml.safe_load_all(template))


def is_connected():
    try:
        version_dict = kube.custom.get_cluster_custom_object("config.openshift.io", "v1",
                                                          "clusterversions", "version")
        logging.debug("Connected to the cluster.")
        return True

    except Exception as e:
        logging.error(e)
        logging.warning("Is the Kubernetes cluster reachable? Aborting.")

        return False


def prepare_settings():
    settings = types.SimpleNamespace()

    logging.info("Settings:")
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings.__dict__[k] = v
        logging.info(f"- {k} = {v}")

    return settings


_artifacts_dir = None
def create_artifact_dir(benchmark_name):
    global _artifacts_dir

    if sys.stdout.isatty():
        base_dir = pathlib.Path("/tmp") / ("matrix-benchmarking" + datetime.datetime.today().strftime("%Y%m%d"))
        base_dir.mkdir(exist_ok=True)
        current_length = len(list(base_dir.glob("*__*")))
        _artifacts_dir = base_dir / f"{current_length:03d}__benchmarking__run_{benchmark_name}"
        _artifacts_dir.mkdir(exist_ok=True)
    else:
        _artifacts_dir = pathlib.Path(os.getcwd())

    src_dir = _artifacts_dir / "src"
    src_dir.mkdir(exist_ok=True)

    logging.info(f"Saving artifacts files into {_artifacts_dir}")


def save_artifact(content, filename, *, is_src=False, mode="w"):
    dest_dir = _artifacts_dir
    if is_src:
        dest_dir /= "src"

    with open(dest_dir / filename, mode) as out_f:
        out_f.write(content)


def save_system_artifacts():
    logging.info("-----")
    logging.info("Collecting system artifacts ...")

    def save_nodes():
        nodes = kube.corev1.list_node()
        nodes_dict = nodes.to_dict()

        try: del nodes_dict["metadata"]["managed_fields"]
        except KeyError: pass # ignore

        try: del nodes_dict["status"]["images"]
        except KeyError: pass # ignore

        save_artifact(yaml.dump(nodes_dict), "nodes.yaml")

    def save_cluster_version():
        logging.info("Saving OpenShift version ...")

        version_dict = kube.custom.get_cluster_custom_object("config.openshift.io", "v1",
                                                          "clusterversions", "version")
        try: del version_dict["metadata"]["managedFields"]
        except KeyError: pass # ignore

        save_artifact(yaml.dump(version_dict), "ocp_version.yaml")

    save_nodes()
    save_cluster_version()


def prepare_prometheus():
    prom_data = types.SimpleNamespace()

    with time_it("restart_prometheus"):
        prom_data.handler = prom.restart_prometheus()
    prom_data.start_ts = prom.query_current_ts(prom_data.handler)

    return prom_data

def finalize_prometheus(prom_data):
    prom_data.end_ts = prom.query_current_ts(prom_data.handler)

    def save_db_raw():
        logging.info("Capturing Prometheus database ...")
        tgz_content = prom.dump_prometheus_db_raw(prom_data.handler)

        dest_tgz = "prometheus_db.tgz"

        save_artifact(tgz_content, dest_tgz, mode="wb")
        db_size = len(tgz_content)
        logging.info(f"Prometheus database saved into '{dest_tgz}' ({db_size/1024/1024:.0f}MB)")

    def save_db_json():
        logging.info("Capturing Prometheus metrics ...")
        db_json = prom.dump_prometheus_db_json(prom_data.handler, prom_data.start_ts, prom_data.end_ts)
        with time_it("prometheus json to file"):
            save_artifact(yaml.dump(db_json), "prometheus_db.json")

        logging.info("Capturing Prometheus metrics ... done.")

    with time_it("save_prometheus_db_raw"):
        save_db_raw()
    #with time_it("save_prometheus_db_json"): save_db_json()


class time_it:
    def __init__(self, msg):
        self.start_time = None
        self.msg = msg

    def __enter__(self):
        self.start_time = datetime.datetime.now()

    def __exit__(self, ex_type, ex_value, ex_tb):
        end_time = datetime.datetime.now()
        seconds = (end_time - self.start_time).seconds
        if seconds < 180:
            time_str = f"{seconds} seconds"
        else:
            time_str = f"{seconds/60:.1f} minutes"
        logging.info(f"time_it: {self.msg}: %s", time_str)
