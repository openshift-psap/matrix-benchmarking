from matrix_view.table_stats import TableStats
from matrix_view.hpc import perf

def register():
    TableStats.ValueDev("speed", "Simulation speed", "speed", ".2f", "ns/day", higher_better=False)

    perf.Plot(mode="mlperf", what="time")
