from ui.table_stats import TableStats

import plugins.adaptive.matrix_view
from plugins.adaptive.matrix_view import parse_data, all_records, get_record

from . import perf

def rewrite_properties(params_dict):
    if "mpi-slots" not in params_dict:
        params_dict["mpi-slots"] = "999"

    NB_CORE_ON_MACHINES = 8

    machines = int(int(params_dict["processes"]) / int(params_dict["mpi-slots"]))
    if machines * int(params_dict["mpi-slots"]) != int(params_dict["processes"]):
        machines += 1
    params_dict["machines"] = str(machines)

    if "network" in params_dict:
        network = params_dict["network"]
        del params_dict["network"]
        if network != "default":
            params_dict["platform"] += f"_{network}"
        else:
            if params_dict["platform"] == "openshift" and network == "default":
                params_dict["platform"] = "openshift_sdn"

    if params_dict["platform"] == "podman":
        params_dict["platform"] = "baremetal_podman"

    del params_dict["processes"]

    if "gpu" in params_dict:
        if params_dict['gpu'].isdigit():
            params_dict["gpu"] = f":{int(params_dict['gpu']):02d}"
        else:
            params_dict['gpu'] = ":"+params_dict['gpu']

    del params_dict['driver']

    if "relyOnSharedFS" not in params_dict:
        params_dict["relyOnSharedFS"] = "False"

    params_dict["run"] = str(params_dict.get("run", 0))+"."
    params_dict["@run"] = params_dict["run"]
    del params_dict["run"]

    params_dict["relyOnSharedFS"] = params_dict["relyOnSharedFS"].lower()


    return params_dict

plugins.adaptive.matrix_view.rewrite_properties = rewrite_properties

def register():
    TableStats.Average("total_time", "Total time", "?.timing",
                       "timing.total_time", ".0f", "in seconds, lower is better")


    perf.Plot(mode="specfem", what="time")
    perf.Plot(mode="specfem", what="speedup")
    perf.Plot(mode="specfem", what="efficiency")
    perf.Plot(mode="specfem", what="time_comparison")
    perf.Plot(mode="specfem", what="strong_scaling")
