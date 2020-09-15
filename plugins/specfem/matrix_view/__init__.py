from ui.table_stats import TableStats

import plugins.adaptive.matrix_view
from plugins.adaptive.matrix_view import parse_data, all_records, get_record

def rewrite_properties(params_dict):
    if "mpi-slots" not in params_dict:
        params_dict["mpi-slots"] = "999"

    NB_CORE_ON_MACHINES = 8
    #params_dict["mpi_slots"] = str(int(NB_CORE_ON_MACHINES/int(params_dict["threads"])))
    params_dict["machines"] = str(1+int(int(params_dict["processes"]) / int(params_dict["mpi-slots"])))

    del params_dict["processes"]

    if "gpu" in params_dict:
        if params_dict['gpu'].isdigit():
            params_dict["gpu"] = f":{int(params_dict['gpu']):02d}"
        else:
            params_dict['gpu'] = ":"+params_dict['gpu']
    else:
        params_dict['gpu'] = 'off'
        
    return params_dict

plugins.adaptive.matrix_view.rewrite_properties = rewrite_properties

def register():
    TableStats.Average("total_time", "Total time", "?.timing",
                       "timing.total_time", ".0f", "s")


