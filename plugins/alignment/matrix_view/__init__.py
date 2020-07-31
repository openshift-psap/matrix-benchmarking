from ui.table_stats import TableStats

import plugins.adaptive.matrix_view
from plugins.adaptive.matrix_view import parse_data, all_records, get_record

plugins.adaptive.matrix_view.rewrite_properties = lambda x:x

def register():

    TableStats.Value("timing_total", "Total runtime", "?.timing",
                       "timing.total", ".0f", "sec")

    TableStats.ValueDev("timing_chunk", "Average runtime", "?.timing",
                       "timing.per_chunk", ".0f", "sec", dev_field="timing.per_chunk_dev")

