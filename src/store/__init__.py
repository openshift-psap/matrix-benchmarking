import common
import copy
import importlib
import datetime
from collections import defaultdict
import sys

experiment_filter = {}
experiment_flags = {
    "--run": False,
    "--parse-only": False,
    "--clean": False,

    "--results-dirname": None,

    "--generate": False,
    "--benchmark-mode": None,

    "--remote-mode": False,
    "--path-tpl": None,
    "--script-tpl": None,
    "--stop-on-error": False,
    "--expe-to-run": [],

}

def load_benchmark_file_flags(benchmark_desc_file):
    for key in experiment_flags:
        value = benchmark_desc_file.get(key)
        if value is None: continue

        experiment_flags[key] = value
        del benchmark_desc_file[key]

    for key, value in benchmark_desc_file.items():
        if not key.startswith("--"): continue
        print(f"WARNING: unexpected flag found in the benchmark file: {key} = '{value}'")


def parse_argv(argv):
    if "--help" in argv:
        print(f"{sys.argv[0]}")
        for k in experiment_flags:
            print(f"{k}")
        sys.exit(0)

    if "run" in argv:
        argv.remove("run")
        experiment_flags["--run"] = True

    for arg in argv:
        if not arg.startswith("--"):
            key, found, value = arg.partition("=")
            if not found:
                raise ValueError(f"Invalid filter: no '=': {arg}")

            experiment_filter[key] = value.split(",")

            continue

        # it's a flag

        if "=" in arg:
            key, _, value = arg.partition("=")
        else:
            key, value = arg, True

        if key not in experiment_flags:
            raise ValueError(f"Unexpected flag: {arg}")

        experiment_flags[key] = value


def load_store():
    print("Loading storage module ...")

    try: importlib.import_module("workload")
    except ModuleNotFoundError as e:
        print(f"FATAL: Failed to load the workload module, is it correctly setup? {e}")
        sys.exit(1)

    try: store_module = importlib.import_module("workload.store")
    except ModuleNotFoundError as e:
        print(f"FATAL: Failed to load the workload.store module, is it correctly setup? {e}")
        sys.exit(1)
    except SyntaxError as e:
        print(f"FATAL: Failed to load the workload.store module: syntax error: {e.filename}:{e.lineno}: {e.text}")
        sys.exit(1)

    print(f"Loading the storage module ... done")
    return store_module


def add_to_matrix(import_settings, location, results, duplicate_handler):
    import_key = common.Matrix.settings_to_key(import_settings)
    if import_key in common.Matrix.import_map:

        try:
            old_location = common.Matrix.import_map[import_key].location
        except AttributeError:
            _, old_location = common.Matrix.import_map[import_key]

        duplicate_handler(import_key, old_location, location)

        return

    try: processed_settings = custom_rewrite_settings(dict(import_settings))
    except Exception as e:
        print(f"ERROR: failed to rewrite settings for entry at '{location}'")
        raise e

    if not processed_settings:
        #print(f"INFO: entry '{import_key}' skipped by rewrite_settings()")
        common.Matrix.import_map[import_key] = True, location
        return

    for filter_name, filter_values in experiment_filter.items():
        if str(processed_settings.get(filter_name, None)) not in filter_values:
            return None

    processed_key = common.Matrix.settings_to_key(processed_settings)

    if processed_key in common.Matrix.processed_map:
        print(f"WARNING: duplicated processed key: {processed_key}")
        print(f"WARNING: duplicated import key:    {import_key}")
        entry = common.Matrix.processed_map[processed_key]
        print(f"WARNING:   old: {entry.location}")
        print(f"WARNING:   new: {location}")
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
        location = entry.location + f"({', '.join(gathered_keys)} gathered)"
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

custom_rewrite_settings = lambda x:x # may be overriden
