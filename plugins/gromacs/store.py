import common
import store
import types

def gromacs_rewrite_settings(params_dict):
    params_dict["machines"] = params_dict["Physical Nodes"]
    del params_dict["Physical Nodes"]
    del params_dict["MPI procs"]
    del params_dict["OMP threads/node"]

    platform = params_dict["platform"]
    if platform == "ocp":
        platform = "openshift"
        network = params_dict["network"]
        del params_dict["network"]
        platform = f"{platform}_{network}"
    elif platform == "bm":
        platform = "baremetal"
    params_dict["platform"] = platform

    if params_dict["isolated-infra"] == "---":
        params_dict["isolated-infra"] = "no"
    if params_dict["isolated-infra"] == "yes":
        params_dict["platform"] += "_isolated_infra"
    del params_dict["isolated-infra"]

    if "network" in params_dict: del params_dict["network"]
    if "network" in all_keys: all_keys.remove("network")

    params_dict["@iteration"] = params_dict["iteration"]
    del params_dict["iteration"]

    return params_dict

store.custom_rewrite_settings = gromacs_rewrite_settings


all_keys = set()
def _populate_matrix(settings_res_lst):
    for params_dict, result, location in settings_res_lst:
        for k in all_keys:
            if k not in params_dict:
                params_dict[k] = "---"

        results = types.SimpleNamespace()
        entry = store.add_to_matrix(params_dict, location, results)
        if not entry: return

        speed_result = result
        time_result = 1/speed_result

        entry.results.speed = speed_result
        entry.results.time = time_result

def parse_data(mode):
    res_file = f"{common.RESULTS_PATH}/{mode}/results.csv"
    settings_res_lst = _parse_file(res_file)
    _populate_matrix(settings_res_lst)

def _parse_file(filename):
    with open(filename) as record_f:
        lines = record_f.readlines()

    settings_res_lst = []

    keys = []
    experiment_settings = {}

    for lineno, _line in enumerate(lines):
        if not _line.replace(',','').strip(): continue # ignore empty lines
        if _line.startswith("##") or _line.startswith('"##'): continue # ignore comments

        line_entries = _line.strip("\n,").split(",") # remove EOL and empty trailing cells

        if _line.startswith("#"):
            # line: # 1536k BM,platform: bm
            experiment_settings = {"experiment": line_entries.pop(0)[1:].strip()}
            for name_value in line_entries:
                name, found, value = name_value.partition(":")
                if not found:
                    print("WARNING: invalid setting for expe "
                          f"'{experiment_settings['expe']}': '{name_value}'")
                    continue
                experiment_settings[name.strip()] = value.strip()
            continue

        if not keys:
            # line: 'Physical Nodes,MPI procs,OMP threads/node,Iterations'
            keys = [k for k in line_entries if k]
            continue

        # line: 1,1,4,0.569,0.57,0.57,0.57,0.569
        # settings ^^^^^| ^^^^^^^^^^^^^^^^^^^^^^^^^ results

        line_settings = dict(zip(keys[:-1], line_entries))
        line_settings.update(experiment_settings)
        line_results = line_entries[len(keys)-1:]
        for ite, result in enumerate(line_results):
            settings = dict(line_settings)
            settings["iteration"] = ite
            try:
                float_result = float(result)
            except ValueError:
                if result:
                    print(f"ERROR: Failed to parse '{result}' for iteration #{ite} of", line_settings)
                continue
            settings_res_lst.append((settings, float_result, f"{filename}:{lineno} iteration#{ite}"))
            pass
        all_keys.update(settings.keys())

    return settings_res_lst
