from matrix_view.table_stats import TableStats
from matrix_view.hpc import perf

def register():
    TableStats.Average("total_time", "Total time", "?.timing",
                       "timing.total_time", ".0f", "in seconds, lower is better")

    perf.Plot(mode="specfem", what="time")
    perf.Plot(mode="specfem", what="speedup")
    perf.Plot(mode="specfem", what="efficiency")
    perf.Plot(mode="specfem", what="time_comparison")
    perf.Plot(mode="specfem", what="strong_scaling")
