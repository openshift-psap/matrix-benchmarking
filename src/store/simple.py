import os
import shutil

import matrix
import common
import store

def _failed_directory(dirname):
    return _incomplete_directory(dirname)

def _incomplete_directory(dirname):
    if not store.experiment_filter.get("__clean__", False):
        return

    shutil.rmtree(dirname)
    print(f"{dirname}: removed")


def _parse_directory(expe, dirname):
    import_settings = {"expe": expe}

    try:
        with open(f"{dirname}/exit_code") as f:
            exit_code = int(f.read().strip())

        if exit_code != 0:
            #print(f"{dirname}: exit_code == {exit_code}, skipping ...")
            _failed_directory(dirname)
            return

    except FileNotFoundError as e:
        if not _incomplete_directory(dirname):
            #print(f"{dirname}: 'exit_code' file not found, skipping ...")
            pass
        return
    except Exception as e:
        print(f"{dirname}: exit_code cannot be read/parsed, skipping ...")
        return

    with open(f"{dirname}/settings") as f:
        for line in f.readlines():
            if not line.strip(): continue

            key, found, value = line.strip().partition("=")
            if not found:
                print(f"ERROR: invalid line in {dirname}/settings:")
                print(f"ERROR: {line.strip()}")
                continue
            import_settings[key] = value
            try:
                if store.experiment_filter[key] != value: return
            except KeyError: pass

    try:
        extra_settings__results = custom_parse_results(dirname, import_settings)
    except Exception as e:
        print(f"ERROR: Failed to parse {dirname} ...")
        print(f"       {e.__class__.__name__}: {e}")
        print()
        raise e
        return

    for extra_settings, results in extra_settings__results:
        entry_import_settings = dict(import_settings)
        entry_import_settings.update(extra_settings)
        entry = store.add_to_matrix(entry_import_settings, dirname, results)
        if not entry: continue

def parse_data(mode):
    path = os.walk(f"{common.RESULTS_PATH}/{mode}/")

    for this_dir, directories, files in path:
        if "skip" in files: continue
        if "settings" not in files: continue

        expe = this_dir.replace(common.RESULTS_PATH+f"/{mode}/", "").partition("/")[0]

        _parse_directory(expe, this_dir)


custom_parse_results = lambda x, y: []
