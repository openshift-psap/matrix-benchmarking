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

    entry = store.add_to_matrix(import_settings, custom_rewrite_settings, dirname)
    if not entry: return

    try:
        custom_parse_results(dirname, entry)
    except Exception as e:
        print(f"ERROR: Failed to parse {dirname} ...")
        raise e


def parse_data(mode, expe_filter):
    path = os.walk(f"{common.RESULTS_PATH}/{mode}/")

    for this_dir, directories, files in path:
        if "skip" in files: continue
        if "properties" not in files: continue

        expe = this_dir.replace(common.RESULTS_PATH+f"/{mode}/", "").partition("/")[0]

        if expe_filter and expe != expe_filter: continue

        _parse_directory(expe, this_dir)


custom_rewrite_settings = lambda x:x # may be overriden
custom_parse_results = lambda x, y: None
