import common

def add_to_matrix(import_settings, rewrite_settings, location):
    import_key = common.Matrix.settings_to_key(import_settings)
    if import_key in common.Matrix.import_map:
        print(f"WARNING: duplicated results key: {import_key}")
        print(f"WARNING:   old: {common.Matrix.import_map[import_key].location}")
        print(f"WARNING:   new: {location}")
        return

    processed_settings = rewrite_settings(import_settings)
    if not processed_settings:
        print(f"INFO: entry '{import_key}' skipped by rewrite_settings()")
        common.Matrix.import_map[import_key] = True
        return

    processed_key = common.Matrix.settings_to_key(processed_settings)

    if processed_key in common.Matrix.processed_map:
        print(f"WARNING: duplicated processed key: {processed_key}")
        print(f"WARNING:   old: {common.Matrix.processed_map[processed_key].location}")
        print(f"WARNING:   new: {location}")
        return

    return common.MatrixEntry(location,
                              processed_key, import_key,
                              processed_settings, import_settings)
