import copy
import importlib
import datetime
from collections import defaultdict
import sys, logging
import pathlib
import inspect

import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.models as models
import matrix_benchmarking.store.simple as store_simple

def load_workload_store(kwargs):
    workload = kwargs["workload"]
    if workload is True:
        raise ValueError("'workload' must have a value ...")

    if workload_base_dir := kwargs.get("workload_base_dir"):
        logging.info(f"Adding workload_base_dir='{workload_base_dir}' to the Python module path list")
        sys.path.insert(0, workload_base_dir)

    try:
        module = f"{workload}.store"
        logging.info(f"Loading {module} module ...")

        store_module = importlib.import_module(module)
    except ModuleNotFoundError:
        logging.error(f"Could not load '{module}' module :/")
        raise

    for fct_name in ("parse_lts_data", "parse_data"):
        if hasattr(store_module, fct_name):
            continue

        setattr(store_module, fct_name, getattr(store_simple, fct_name))

    logging.info(f"Loading {module} module ... done.")

    return store_module


def should_be_filtered_out(settings):
    for key, _value in settings.items():
        if key not in cli_args.experiment_filters:
            # Keep it
            continue
        value = str(_value)
        filter_value = cli_args.experiment_filters[key]
        if isinstance(filter_value, list):
            if value in filter_value:
                continue # Keep it

        elif filter_value == value:
            continue # Keep it

        # Skip it
        return True

    return False


def add_to_matrix(import_settings, location, results, exit_code, duplicate_handler, matrix=common.Matrix):
    if should_be_filtered_out(import_settings):
        return

    import_key = matrix.settings_to_key(import_settings)

    if import_key in matrix.import_map:
        old_entry = matrix.import_map[import_key]

        old_location = getattr(old_entry, "location", None)

        duplicate_handler(import_key, old_entry, old_location, results, location)

        return

    is_lts = matrix != common.Matrix
    try: processed_settings = _rewrite_settings(dict(import_settings), results, is_lts)
    except Exception as e:
        logging.error(f"failed to rewrite settings for entry at '{location}'")
        raise e

    if not processed_settings:
        #logging.info(f"entry '{import_key}' skipped by rewrite_settings()")
        matrix.import_map[import_key] = True, location
        return

    if should_be_filtered_out(processed_settings):
        return

    processed_key = matrix.settings_to_key(processed_settings)

    if processed_key in matrix.processed_map:
        logging.warning(f"duplicated processed key: {processed_key}")
        logging.warning(f"duplicated import key:    {import_key}")
        entry = matrix.processed_map[processed_key]
        logging.warning(f"  old: {entry.location}")
        logging.warning(f"  new: {location}")
        matrix.import_map[import_key] = entry

        processed_settings["run"] = (str(processed_settings.get("run")) + "_" +
                                     datetime.datetime.now().strftime("%H%M%S.%f"))
        processed_key = matrix.settings_to_key(processed_settings)
        return

    entry = common.MatrixEntry(location, results, exit_code,
                               processed_key, import_key,
                               processed_settings, import_settings,
                               matrix=matrix)

    gather_rolling_entries(entry, matrix=matrix)

    return entry

def gather_rolling_entries(entry, matrix=common.Matrix):
    gathered_settings = dict(entry.settings.__dict__)
    gathered_keys = []
    for k in gathered_settings.keys():
        if not k.startswith("@"): continue
        gathered_settings[k] = "<all>"
        gathered_keys.append(k)

    if not gathered_keys: return

    gathered_entry = matrix.get_record(gathered_settings)
    if not gathered_entry:
        processed_key = matrix.settings_to_key(gathered_settings)
        import_key = None
        import_settings = None
        location = entry.location
        gathered_entry = common.MatrixEntry(
            location, [], None,
            processed_key, import_key,
            gathered_settings, import_settings,
            matrix=matrix,
        )
        gathered_entry.is_gathered = True
        gathered_entry.gathered_keys = defaultdict(set)

    gathered_entry.results.append(entry)
    for gathered_key in gathered_keys:
        gathered_entry.gathered_keys[gathered_key].add(entry.settings.__dict__[gathered_key])


# ---

custom_rewrite_settings = None

def _rewrite_settings(import_settings, results, is_lts):
    if custom_rewrite_settings is None:
        logging.warning("No rewrite_setting function registered.")
        return import_settings

    if "results" not in inspect.signature(custom_rewrite_settings).parameters:
        return custom_rewrite_settings(import_settings)

    return custom_rewrite_settings(import_settings, results, is_lts)


def register_custom_rewrite_settings(fn):
    global custom_rewrite_settings
    custom_rewrite_settings = fn

# --

lts_schema = None

def register_lts_schema(schema):
    global lts_schema
    lts_schema = schema


def get_lts_schema():
    if lts_schema is None:
        logging.warning("No LTS schema registered")


    return lts_schema

# ---
