import os

import matrix
import common
import store

def _parse_directory(expe, dirname):
    import_settings = {"expe": expe}
    with open(f"{dirname}/properties") as f:
        for line in f.readlines():
            if not line.strip(): continue

            key, found, value = line.strip().partition("=")
            if not found:
                print(f"ERROR: invalid line in {dirname}/properties:")
                print(f"ERROR: {line.strip()}")
            import_settings[key] = value

    try:
        extra_settings__results = custom_parse_results(dirname, import_settings)
    except Exception as e:
        print(f"ERROR: Failed to parse {dirname} ...")
        raise e

    for extra_settings, results in extra_settings__results:
        entry_import_settings = dict(import_settings)
        entry_import_settings.update(extra_settings)
        entry = store.add_to_matrix(entry_import_settings, dirname, results)
        if not entry: continue

        has_rolling = [k for k in common.Matrix.properties if k.startswith("@")]
        if has_rolling:
            store.gather_rolling_entries(entry)


def parse_data(mode, expe_filter):
    path = os.walk(f"{common.RESULTS_PATH}/{mode}/")

    for this_dir, directories, files in path:
        if "skip" in files: continue
        if "properties" not in files: continue

        expe = this_dir.replace(common.RESULTS_PATH+f"/{mode}/", "").partition("/")[0]

        if expe_filter and expe != expe_filter: continue

        _parse_directory(expe, this_dir)


custom_parse_results = lambda x, y: None
