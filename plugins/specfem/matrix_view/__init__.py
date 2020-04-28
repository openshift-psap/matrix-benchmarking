from ui.table_stats import TableStats

import plugins.adaptive.matrix_view
from plugins.adaptive.matrix_view import parse_data, all_records, get_record

plugins.adaptive.matrix_view.rewrite_properties = lambda x:x

def register():

    TableStats.Average("sys_mem_avg", "Free Memory (avg)", "?.mem",
                       "mem.free", ".0f", "MB")

    TableStats.Average("sys_cpu_avg", "System CPU Usage (avg)", "?.cpu",
                       "cpu.idle", ".0f", "%")

    TableStats.Average(f"spec_cpu", f"Specfem CPU Usage (avg)", f"?.local-pid",
                       f"local-pid.cpu", ".0f", "%")

    TableStats.Average(f"general_time", f"Overall time", "?.general",
                       "general.specfem_time", ".0f", "sec")
