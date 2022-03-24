import copy
import importlib
import datetime
from collections import defaultdict
import sys, logging
import pathlib

import matrix_benchmarking.common as common
from matrix_benchmarking.common import Matrix

experiment_filter = {}

def parse_argv(argv):
    # it's a flag

    if "=" in arg:
        key, _, value = arg.partition("=")
    else:
        key, value = arg, True

    if key not in experiment_flags:
        raise ValueError(f"Unexpected flag: {arg}")

    experiment_flags[key] = value


def load_workload_store(kwargs):
    workload = kwargs["workload"]
    module = f"matrix_benchmarking.workloads.{workload}.store"
    logging.info(f"Loading '{module}' module ...")

    store_module = importlib.import_module(module)

    logging.info(f"Loading '{module}' module ... done.")

    return store_module


def add_to_matrix(import_settings, _location, results, duplicate_handler):
    import_key = Matrix.settings_to_key(import_settings)
    location = pathlib.Path(_location)

    if import_key in Matrix.import_map:
        try:
            old_location = Matrix.import_map[import_key].location
        except AttributeError:
            _, old_location = Matrix.import_map[import_key]

        duplicate_handler(import_key, old_location, location)

        return

    try: processed_settings = _rewrite_settings(dict(import_settings))
    except Exception as e:
        logging.error(f"failed to rewrite settings for entry at '{location}'")
        raise e

    if not processed_settings:
        #logging.info(f"entry '{import_key}' skipped by rewrite_settings()")
        Matrix.import_map[import_key] = True, location
        return

    for filter_name, filter_values in experiment_filter.items():
        if str(processed_settings.get(filter_name, None)) not in filter_values:
            return None

    processed_key = Matrix.settings_to_key(processed_settings)

    if processed_key in common.Matrix.processed_map:
        logging.warning(f"duplicated processed key: {processed_key}")
        logging.warning(f"duplicated import key:    {import_key}")
        entry = common.Matrix.processed_map[processed_key]
        logging.warning(f"  old: {entry.location}")
        logging.warning(f"  new: {location}")
        common.Matrix.import_map[import_key] = entry

        processed_settings["run"] = (str(processed_settings.get("run")) + "_" +
                                     datetime.datetime.now().strftime("%H%M%S.%f"))
        processed_key = common.Matrix.settings_to_key(processed_settings)
        return

    entry = common.MatrixEntry(location, results,
                              processed_key, import_key,
                              processed_settings, import_settings)

    gather_rolling_entries(entry)

    return entry

def gather_rolling_entries(entry):
    gathered_settings = dict(entry.params.__dict__)
    gathered_keys = []
    for k in gathered_settings.keys():
        if not k.startswith("@"): continue
        gathered_settings[k] = "<all>"
        gathered_keys.append(k)

    if not gathered_keys: return

    gathered_entry = common.Matrix.get_record(gathered_settings)
    if not gathered_entry:
        processed_key = common.Matrix.settings_to_key(gathered_settings)
        import_key = None
        import_settings = None
        location = entry.location
        gathered_entry = common.MatrixEntry(
            location, [],
            processed_key, import_key,
            gathered_settings, import_settings
        )
        gathered_entry.is_gathered = True
        gathered_entry.gathered_keys = defaultdict(set)

    gathered_entry.results.append(entry)
    for gathered_key in gathered_keys:
        gathered_entry.gathered_keys[gathered_key].add(entry.params.__dict__[gathered_key])


# ---

custom_rewrite_settings = None

def _rewrite_settings(dirname):
    if custom_rewrite_settings is None:
        logging.warning("No rewrite_setting function registered.")
        return

    return custom_rewrite_settings(dirname)

def register_custom_rewrite_settings(fn):
    global custom_rewrite_settings
    custom_rewrite_settings = fn

# ---
