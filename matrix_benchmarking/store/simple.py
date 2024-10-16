import os
import shutil
import logging
import pathlib
import yaml
import json
import types

import pydantic

import matrix_benchmarking.matrix as matrix
import matrix_benchmarking.common as common
import matrix_benchmarking.store as store
import matrix_benchmarking.cli_args as cli_args
from matrix_benchmarking import download_lts

def invalid_directory(dirname, settings, reason, warn=False):
    run_flag = cli_args.kwargs.get("run")
    clean_flag = cli_args.kwargs.get("clean")
    benchmark_mode = cli_args.kwargs["execution_mode"]

    if warn or clean_flag:
        logging.info("%s", dirname)
        logging.info("%s", ", ".join(f"{k}={v}" for k, v in settings.items()))
        logging.info("\t\tis invalid: %s", reason)
        logging.info("")

    if benchmark_mode: return
    if not run_flag: return
    if not clean_flag: return

    shutil.rmtree(dirname)
    logging.info(f"{dirname}: removed ({reason})")


def _duplicated_directory(import_key, old_entry, old_location, new_results, new_location):
    logging.warning(f"duplicated results key: {import_key}")
    logging.warning(f"  old: {old_location}")
    logging.warning(f"  new: {new_location}")

    if not cli_args.kwargs.get("clean"):
        return

    if not cli_args.kwargs["run"]:
        logging.info(f"{new_location} would have been deleted.")
        return

    shutil.rmtree(new_location)
    logging.info(f"{new_location}: removed")


def parse_old_settings(filename):
    settings = {}
    with open(filename) as f:
        for line in f.readlines():
            if not line.strip(): continue

            key, found, value = line.strip().partition("=")
            if not found:
                logging.error(f"Cannot parse setting from {filename}: invalid line (no '='): {line.strip()}")
                continue

            settings[key] = value

    return settings


def parse_settings(dirname):
    import_settings = {}

    # search for settings[.*] in dirname and all of its parent directories.
    # start in the top-most parent, so that each subdirectory overrides its parents.
    for parent_dir in list(reversed([dirname] + list(dirname.parents))):
        for filename in list(parent_dir.glob("settings")) + list(parent_dir.glob("settings.*")):
            if filename.suffix not in (".yaml", ".yml"): # deprecated
                logging.debug(f"Found deprecated 'settings' file in {dirname}: {filename}")

                import_settings.update(parse_old_settings(filename))
                continue
            with open(filename) as f:
                settings = yaml.safe_load(f)
            import_settings.update(settings)

    return import_settings


def _parse_directory(results_dir, dirname):
    import_settings = parse_settings(dirname)

    if store.should_be_filtered_out(import_settings):
        return

    exit_code = -1
    try:
        with open(dirname / "exit_code") as f:
            content = f.read().strip()
            if not content:
                logging.info(f"{dirname}: exit_code is empty, skipping ...")
                return

        exit_code = int(content)
    except FileNotFoundError as e:
        invalid_directory(dirname, import_settings, "exit_code not found")
        return

    except Exception as e:
        logging.info(f"{dirname}: exit_code cannot be read/parsed, skipping ... ({e})")
        return

    def add_to_matrix(results, extra_settings=None):
        if extra_settings:
            entry_import_settings = dict(import_settings)
            entry_import_settings.update(extra_settings)
        else:
            entry_import_settings = import_settings

        store.add_to_matrix(entry_import_settings,
                            pathlib.Path(dirname),
                            results, exit_code,
                            _duplicated_directory)

    try:
        extra_settings__results = _parse_results(add_to_matrix, dirname, import_settings, exit_code)
    except Exception as e:
        logging.error(f"Failed to parse {dirname} ...")
        logging.info(f"       {e.__class__.__name__}: {e}")
        logging.info("")
        raise e


# ---

custom_parse_results = None
custom_build_lts_payloads = None

def _parse_results(add_to_matrix, dirname, import_settings, exit_code):
    if custom_parse_results is None:
        raise RuntimeError("simple store: No data parser registered :/")

    return custom_parse_results(add_to_matrix, dirname, import_settings, exit_code)

def build_lts_payloads():
    if custom_build_lts_payloads is None:
        raise RuntimeError("simple store: No payload builder registered :/")

    return custom_build_lts_payloads()

def register_custom_parse_results(fn):
    global custom_parse_results
    custom_parse_results = fn

def register_custom_build_lts_payloads(fn):
    global custom_build_lts_payloads
    custom_build_lts_payloads = fn

# ---
# Borrowed from:
# https://dev.to/taqkarim/extending-simplenamespace-for-nested-dictionaries-58e8

# Similar to SimpleNamespace, but RecursiveNamespace.map_entry recursively creates namespaces from nested dicts
class RecursiveNamespace(types.SimpleNamespace):

    @staticmethod
    def map_entry(entry):
        if isinstance(entry, dict):
            return RecursiveNamespace(**entry)

        return entry

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for key, val in kwargs.items():
            if type(val) == dict:
                setattr(self, key, RecursiveNamespace(**val))
            elif type(val) == list:
                setattr(self, key, list(map(self.map_entry, val)))


def parse_lts_data(lts_results_dir=None):
    if lts_results_dir is None:
        lts_results_dir = pathlib.Path(cli_args.kwargs["lts_results_dirname"])

    def has_lts_anchor(files):
        return download_lts.LTS_ANCHOR_NAME in files

    path = os.walk(lts_results_dir, followlinks=True)
    for _this_dir, directories, files in path:
        this_dir = pathlib.Path(_this_dir)
        if "skip" in files: continue
        if not has_lts_anchor(files): continue

        with open(this_dir / download_lts.LTS_ANCHOR_NAME) as f:
            lts_anchor = yaml.safe_load(f)

        for filename in files:
            if filename == download_lts.LTS_ANCHOR_NAME: continue
            if filename.startswith("."): continue

            filepath = this_dir / filename
            with open(filepath) as f:
                document = json.load(f)

            lts_payload = RecursiveNamespace.map_entry(document)

            lts_settings = lts_payload.metadata.settings

            import_settings = dict(lts_settings.__dict__)

            import_settings["@timestamp"] = str(lts_payload.metadata.start)

            exit_code = getattr(lts_payload.metadata, "exit_code", None)

            def _duplicated_entry(import_key, old_entry, old_location, new_results, new_location):
                logging.warning(f"duplicated results key: {import_key}")

                logging.warning(f"  old: {old_location} | {old_entry.results.metadata.test_uuid}")
                logging.warning(f"  new: {new_location} | {new_results.metadata.test_uuid}")

            store.add_to_matrix(import_settings, filepath,
                                lts_payload, exit_code,
                                _duplicated_entry,
                                matrix=common.LTS_Matrix)
        pass
# ---

def parse_data(results_dir=None):
    if results_dir is None:
        results_dir = pathlib.Path(cli_args.kwargs["results_dirname"])

    if not results_dir.exists():
        raise FileNotFoundError(f"Results directory '{results_dir}' does not exist.")

    if not results_dir.is_dir():
        raise FileNotFoundError(f"Results directory '{results_dir}' is not a directory ...")

    def has_settings(files):
        if "settings" in files:
            logging.debug(f"Found deprecated 'settings' file ...")
            return True # deprecated
        if "settings.yml" in files:
            logging.warning(f"Found settings file with invalid extention 'settings.yml' file ...")
            return True

        if "settings.yaml" in files: return True

        return False

    results_directories = []
    path = os.walk(results_dir, followlinks=True)
    for _this_dir, directories, files in path:
        if "skip" in files: continue
        if not has_settings(files): continue

        this_dir = pathlib.Path(_this_dir)

        is_subdir_of_results_dir = False
        for existing_results_directory in results_directories:
            if existing_results_directory in this_dir.parents:
                is_subdir_of_results_dir = True
                break
        if is_subdir_of_results_dir:
            # we don't want nested results dirs
            continue

        relative = this_dir.relative_to(results_dir)

        results_directories.append(this_dir)
        _parse_directory(results_dir, this_dir)
