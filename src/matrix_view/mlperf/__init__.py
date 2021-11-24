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

        time_to_threshold.MigThresholdOverTime()
        time_to_threshold.MigTimeToThreshold()
        time_to_threshold.MigTimeToThreshold(speed=True)

        for mig_type in ("1g.5gb", "2g.10gb", "3g.20gb"):
            time_to_threshold.MigThresholdOverTime(mig_type)
            time_to_threshold.MigTimeToThreshold(mig_type)
            time_to_threshold.MigTimeToThreshold(mig_type, speed=True)

    elif store.experiment_filter.get("benchmark", "burn") == "burn":
        TableStats.ValueDev("speed", "Speed", "speed", ".0f", "Gflop/s", higher_better=True)

    prom_overview.Plot(metric='DCGM_FI_PROF_GR_ENGINE_ACTIVE', y_title="% of the of the graphic engine active")
    prom_overview.Plot(metric='DCGM_FI_PROF_DRAM_ACTIVE', y_title="% of cycles the memory is active (tx/rx)")
    prom_overview.Plot(metric='DCGM_FI_DEV_POWER_USAGE', y_title="Watt")

    #prom_overview.Plot(metric='cluster:cpu_usage_cores:sum', y_title="# of cores")
