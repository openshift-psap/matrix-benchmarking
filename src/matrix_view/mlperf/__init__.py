from matrix_view.table_stats import TableStats
from matrix_view.hpc import perf
from matrix_view.prom import overview as prom_overview
from matrix_view.mlperf import time_to_threshold
import store

def register():
    if store.experiment_filter.get("benchmark", "ssd") == "ssd":
        TableStats.ValueDev("speed", "Speed", "avg_sample_sec", ".2f", "avg. samples / sec", higher_better=True)
        TableStats.ValueDev("exec_time", "Execution Time", "exec_time", ".2f", "minutes", divisor=60, higher_better=False)

        time_to_threshold.Plot()

    elif store.experiment_filter.get("benchmark", "burn") == "burn":
        TableStats.ValueDev("speed", "Speed", "speed", ".0f", "Gflop/s", higher_better=True)

    prom_overview.Plot(metric='DCGM_FI_DEV_POWER_USAGE', y_title="Watt")
    prom_overview.Plot(metric='cluster:cpu_usage_cores:sum', y_title="# of cores")
