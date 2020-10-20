import types
from ui.matrix_view import Matrix
from ui.table_stats import TableStats
from plugins.adaptive.matrix_view import parse_data, all_records, get_record
import plugins.adaptive.matrix_view as mv

FileEntry = types.SimpleNamespace
Params = types.SimpleNamespace
all_keys = set()
def rewrite_properties(params_dict):
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

    del params_dict["experiment"]

    if "network" in params_dict: del params_dict["network"]
    if "network" in all_keys: all_keys.remove("network")

    params_dict["@iteration"] = params_dict["iteration"]
    del params_dict["iteration"]

    return params_dict

def populate_matrix(props_res_lst):
    for params_dict, result in props_res_lst:
        entry = FileEntry()
        entry.params = Params()

        for k in all_keys:
            if k not in params_dict:
                params_dict[k] = "---"

        params_dict = rewrite_properties(params_dict)
        if params_dict is None:
            print(f"Skip (rewrite_properties) {entry.key}")
            continue

        if mv.key_order is None:
            mv.key_order = list(params_dict.keys())

        entry.key = "_".join([f"{k}={params_dict.get(k)}" for k in mv.key_order])
        entry.params.__dict__.update(params_dict)

        entry.filename = entry.linkname = "[not available]"
        try:
            dup_entry = Matrix.entry_map[entry.key]
            print(f"WARNING: duplicated key:")
            print(f"\t 1: {dup_entry.key}")
            print(f"\t 2: {entry.key}")
            continue
        except KeyError: pass # not duplicated

        speed_result = result
        time_result = 1/speed_result * 200

        table_name = "timing"
        entry.tables = {
            f"#worker.{table_name}|{table_name}.total_time,{table_name}.speed":
                                            (table_name, [[time_result, speed_result]])
        }

        for param, value in entry.params.__dict__.items():
            try: value = int(value)
            except ValueError: pass # not a number, keep it as a string
            except TypeError: str(value) # cannot be parsed with int(), convert it to string
            Matrix.properties[param].add(value)

        Matrix.entry_map[entry.key] = entry

        entry.stats = {}
        for table_stat in TableStats.all_stats:

            if isinstance(table_stat, TableStats):
                register = False
                for table_def, (table_name, table_rows) in entry.tables.items():
                    if (table_stat.table != table_name and not
                        (table_stat.table.startswith("?.") and table_name.endswith(table_stat.table[1:]))):
                        continue
                    entry.stats[table_stat.name] = table_stat.process(table_def, table_rows)
                    register = True
            else: register = True

            if register:
                Matrix.properties["stats"].add(table_stat.name)

def parse_data():
    props_res_lst = parse_file("results/gromacs.csv")
    populate_matrix(props_res_lst)

def parse_file(filename):
    with open(filename) as record_f:
        lines = record_f.readlines()

    props_res_lst = []

    keys = []
    experiment_properties = {}

    for _line in lines:
        if not _line.replace(',','').strip(): continue # ignore empty lines
        if _line.startswith("##") or _line.startswith('"##'): continue # ignore comments

        line_entries = _line.strip("\n,").split(",") # remove EOL and empty trailing cells

        if _line.startswith("#"):
            # line: # 1536k BM,platform: bm
            experiment_properties = {"experiment": line_entries.pop(0)[1:].strip()}
            for prop_value in line_entries:
                prop, found, value = prop_value.partition(":")
                if not found:
                    print("WARNING: invalid property for expe "
                          f"'{experiment_properties['experiment']}': '{prop_value}'")
                    continue
                experiment_properties[prop.strip()] = value.strip()
            continue

        if not keys:
            # line: 'Physical Nodes,MPI procs,OMP threads/node,Iterations'
            keys = [k for k in line_entries if k]
            continue

        # line: 1,1,4,0.569,0.57,0.57,0.57,0.569
        # props ^^^^^| ^^^^^^^^^^^^^^^^^^^^^^^^^ results

        line_properties = dict(zip(keys[:-1], line_entries))
        line_properties.update(experiment_properties)
        line_results = line_entries[len(keys)-1:]
        for i, result in enumerate(line_results):
            props = dict(line_properties)
            props["iteration"] = i
            try:
                float_result = float(result)
            except ValueError:
                if result:
                    print(f"ERROR: Failed to parse '{result}' for iteration #{i} of", line_properties)
                continue
            props_res_lst.append((props, float_result))
            pass
        all_keys.update(props.keys())

    return props_res_lst

def register():
    import plugins.specfem.matrix_view.perf as perf
    TableStats.Average("speed", "Simulation speed", "?.timing", "timing.speed", ".2f", "ns/day")
    TableStats.Average("time", "Simulation time", "?.timing", "timing.total_time", ".2f", "s")


    perf.Plot(mode="gromacs", what="time")
    perf.Plot(mode="gromacs", what="speedup")
    perf.Plot(mode="gromacs", what="efficiency")
    perf.Plot(mode="gromacs", what="time_comparison")
    perf.Plot(mode="gromacs", what="strong_scaling")
