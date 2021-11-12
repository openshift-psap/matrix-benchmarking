import common
import copy
import importlib
import datetime

experiment_filter = {}

DEFAULT_MODE = "mlperf"
def parse_argv(argv):
    for expe_filter in argv:
        if expe_filter == "run":
            key, value = "__run__", True
        elif expe_filter == "clean":
            key, value = "__clean__", True
        elif expe_filter == "parse_only":
            key, value = "__parse_only__", True
        elif "=" not in expe_filter:
            if "expe" in experiment_filter:
                raise ValueError(f"Unexpected argument '{expe_filter}'")
            key, value = "expe", expe_filter
        else:
            key, _, value = expe_filter.partition("=")

        experiment_filter[key] = value

    return experiment_filter.pop("mode", DEFAULT_MODE)

def mode_store(mode):
    print(f"Loading {mode} storage module ...")
    store_pkg_name = f"store.{mode}"
    try: store_plugin = importlib.import_module(store_pkg_name)
    except ModuleNotFoundError as e:
        print(f"FATAL: Failed to load module '{mode}': {e}")
        raise e

    print(f"Loading {mode} storage module ... done")
    return store_plugin

def add_to_matrix(import_settings, location, results):
    import_key = common.Matrix.settings_to_key(import_settings)
    if import_key in common.Matrix.import_map:
        print(f"WARNING: duplicated results key: {import_key}")
        try:
            old_location = common.Matrix.import_map[import_key].location
        except AttributeError:
            _, old_location = common.Matrix.import_map[import_key]

        print(f"WARNING:   old: {old_location}")
        print(f"WARNING:   new: {location}")
        return

    try: processed_settings = custom_rewrite_settings(import_settings)
    except Exception as e:
        print(f"ERROR: failed to rewrite settings for entry at '{location}'")
        raise e

    if not processed_settings:
        #print(f"INFO: entry '{import_key}' skipped by rewrite_settings()")
        common.Matrix.import_map[import_key] = True, location
        return

    keep = True
    for k, v in experiment_filter.items():
        if k.startswith("__"): continue
        if str(processed_settings.get(k, None)) != v:
            return None

    processed_key = common.Matrix.settings_to_key(processed_settings)

    if processed_key in common.Matrix.processed_map:
        print(f"WARNING: duplicated processed key: {processed_key}")
        print(f"WARNING:   old: {common.Matrix.processed_map[processed_key].location}")
        print(f"WARNING:   new: {location}")
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
    gathered_entry.results.append(entry)

custom_rewrite_settings = lambda x:x # may be overriden
