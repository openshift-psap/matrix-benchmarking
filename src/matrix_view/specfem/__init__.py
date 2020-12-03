from matrix_view.table_stats import TableStats
from matrix_view.hpc import perf

def register():
    TableStats.ValueDev(id_name="total_time", name="Total time",
                        field="time", fmt=".0f", unit="seconds",
                        higher_better=False)

    perf.Plot(mode="specfem", what="time")
    perf.Plot(mode="specfem", what="speedup")
    perf.Plot(mode="specfem", what="efficiency")
    perf.Plot(mode="specfem", what="time_comparison")
    perf.Plot(mode="specfem", what="strong_scaling")
