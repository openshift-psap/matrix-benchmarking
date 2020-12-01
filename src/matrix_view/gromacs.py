from matrix_view.table_stats import TableStats
from matrix_view.hpc import perf

def register():
    TableStats.Average("speed", "Simulation speed", "?.timing", "timing.speed", ".2f", "ns/day")
    TableStats.Average("time", "Simulation time", "?.timing", "timing.total_time", ".2f", "s")


    perf.Plot(mode="gromacs", what="time")
    perf.Plot(mode="gromacs", what="speedup")
    perf.Plot(mode="gromacs", what="efficiency")
    perf.Plot(mode="gromacs", what="time_comparison")
    perf.Plot(mode="gromacs", what="strong_scaling")
