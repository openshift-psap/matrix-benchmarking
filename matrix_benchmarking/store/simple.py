import os
import shutil
import logging
import pathlib

import matrix_benchmarking.matrix as matrix
import matrix_benchmarking.common as common
import matrix_benchmarking.store as store
import matrix_benchmarking.cli_args as cli_args

def _failed_directory(dirname):
    return _incomplete_directory(dirname)

def _incomplete_directory(dirname):
    if not cli_args.kwargs.get("clean"):
        return
    if not cli_args.kwargs["run"]:
        logging.info(f"{dirname} would have been deleted.")
        return

    shutil.rmtree(dirname)
    logging.info(f"{dirname}: removed")

def _duplicated_directory(import_key, old_location, new_location):
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

def _parse_directory(expe, dirname):
    import_settings = {"expe": expe}

    try:
        with open(dirname / "exit_code") as f:
            exit_code = int(f.read().strip())

        if exit_code != 0:
            logging.debug(f"{dirname}: exit_code == {exit_code}, skipping ...")
            _failed_directory(dirname)
            return

    except FileNotFoundError as e:
        if not _incomplete_directory(dirname):
            logging.debug(f"{dirname}: 'exit_code' file not found, skipping ...")
            pass
        return
    except Exception as e:
        logging.info(f"{dirname}: exit_code cannot be read/parsed, skipping ...")
        return

    with open(dirname / "settings") as f:
        for line in f.readlines():
            if not line.strip(): continue

            key, found, value = line.strip().partition("=")
            if not found:
                logging.error(f"invalid line in {dirname}/settings:")
                logging.error(f"{line.strip()}")
                continue
            import_settings[key] = value
            try:
                if store.experiment_filter[key] != value: return
            except KeyError: pass

    def add_to_matrix(results, extra_settings=None):
        if extra_settings:
            entry_import_settings = dict(import_settings)
            entry_import_settings.update(extra_settings)
        else:
            entry_import_settings = import_settings

        store.add_to_matrix(entry_import_settings,
                            pathlib.Path(dirname),
                            results,
                            _duplicated_directory)

    try:
        extra_settings__results = _parse_results(add_to_matrix, dirname, import_settings)
    except Exception as e:
        logging.error(f"Failed to parse {dirname} ...")
        logging.info(f"       {e.__class__.__name__}: {e}")
        logging.info("")
        raise e

# ---

custom_parse_results = None

def _parse_results(add_to_matrix, dirname, import_settings):
    if custom_parse_results is None:
        raise RuntimeError("simple store: No data parser registered :/")


    return custom_parse_results(add_to_matrix, dirname, import_settings)

def register_custom_parse_results(fn):
    global custom_parse_results
    custom_parse_results = fn

# ---

def parse_data(results_dirname):
    results_dir = common.RESULTS_PATH / results_dirname

    path = os.walk(results_dir)

    for _this_dir, directories, files in path:
        if "skip" in files: continue
        if "settings" not in files: continue

        this_dir = pathlib.Path(_this_dir)
        expe = this_dir.relative_to(results_dir).parents[-2].name

        _parse_directory(expe, this_dir)
