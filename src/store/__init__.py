import common
import copy

experiment_filter = {}

def add_to_matrix(import_settings, location, results):
    import_key = common.Matrix.settings_to_key(import_settings)
    if import_key in common.Matrix.import_map:
        print(f"WARNING: duplicated results key: {import_key}")
        print(f"WARNING:   old: {common.Matrix.import_map[import_key].location}")
        print(f"WARNING:   new: {location}")
        return

    processed_settings = custom_rewrite_settings(import_settings)
    if not processed_settings:
        print(f"INFO: entry '{import_key}' skipped by rewrite_settings()")
        common.Matrix.import_map[import_key] = True
        return

    keep = True
    for k, v in experiment_filter.items():
        if str(processed_settings.get(k, None)) != v:
            return None

    processed_key = common.Matrix.settings_to_key(processed_settings)

    if processed_key in common.Matrix.processed_map:
        print(f"WARNING: duplicated processed key: {processed_key}")
        print(f"WARNING:   old: {common.Matrix.processed_map[processed_key].location}")
        print(f"WARNING:   new: {location}")
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
