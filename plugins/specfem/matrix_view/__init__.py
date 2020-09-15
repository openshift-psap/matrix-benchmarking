from ui.table_stats import TableStats

import plugins.adaptive.matrix_view
from plugins.adaptive.matrix_view import parse_data, all_records, get_record

def rewrite_properties(params_dict):
    del params_dict["processes"]
    del params_dict["threads"]

    return params_dict

plugins.adaptive.matrix_view.rewrite_properties = rewrite_properties

def register():
    TableStats.Average("total_time", "Total time", "?.timing",
                       "timing.total_time", ".0f", "s")


