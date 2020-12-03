from matrix_view.table_stats import TableStats
from matrix_view.hpc import perf

def register():
    TableStats.ValueDev("speed", "Simulation speed", "speed", ".2f", "ns/day", higher_better=False)
    TableStats.ValueDev("time", "Simulation time", "total_time", ".2f", "s", higher_better=False)


    perf.Plot(mode="gromacs", what="time")
    perf.Plot(mode="gromacs", what="speedup")
    perf.Plot(mode="gromacs", what="efficiency")
    perf.Plot(mode="gromacs", what="time_comparison")
    perf.Plot(mode="gromacs", what="strong_scaling")
