import types, datetime
import yaml

import matrix_benchmarking.store as store
import matrix_benchmarking.store.simple as store_simple

def _sample_rewrite_settings(params_dict):
    # add a @ on top of parameter name 'run'
    # to treat it as multiple identical executions

    params_dict["@run"] = params_dict["run"]
    del params_dict["run"]

    # if parameter 'run' was missing, set '0' as default value
    if params_dict["@run"] == "":
        params_dict["@run"] = "0"

    # overwrite 'operation' parameter
    mode = params_dict.pop("mode")
    op = params_dict.pop("operation")
    params_dict["operation"] = f"{mode}-{op}"

    # remove the 'expe' setting
    params_dict.pop("expe")

    return params_dict

def __parse_date(dirname, settings):
    results = types.SimpleNamespace()

    with open(dirname / "date") as f:
        results.date_ts = int(f.readlines()[0])

    return results

def __parse_procs(dirname, settings):
    results = types.SimpleNamespace()

    with open(dirname / "procs") as f:
        results.procs = int(f.readlines()[0])

    return results

def __parse_memfree(dirname, settings):
    results = types.SimpleNamespace()

    with open(dirname / "memfree") as f:
        results.memfree = int(f.readlines()[0]) * 1000 # unit if kB

    return results

def _sample_parse_results(fn_add_to_matrix, dirname, import_settings):
    mode = import_settings.get("mode")
    if not mode:
        print(f"ERROR: failed to parse '{dirname}', 'mode' setting not defined.")
        return

    mode_fct = {
        "date":  __parse_date,
        "procs": __parse_procs,
        "memfree":  __parse_memfree,
    }

    fct = mode_fct.get(mode)
    if not fct:
        print(f"ERROR: failed to parse '{dirname}', mode={mode} not recognized.")
        return

    results = fct(dirname, import_settings)
    fn_add_to_matrix(results)

# delegate the parsing to the simple_store
def parse_data(results_dirname):
    store.register_custom_rewrite_settings(_sample_rewrite_settings)
    store_simple.register_custom_parse_results(_sample_parse_results)

    return store_simple.parse_data(results_dirname)
