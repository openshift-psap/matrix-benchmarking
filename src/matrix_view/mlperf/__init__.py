from matrix_view.table_stats import TableStats
from matrix_view.hpc import perf
from matrix_view.prom import overview as prom_overview
from matrix_view.mlperf import time_to_threshold
from matrix_view.mlperf import report
import store

def register():
    TableStats.ValueDev("speed", "Speed", "avg_sample_sec", ".2f", "avg. samples / sec", higher_better=True)
    TableStats.ValueDev("exec_time", "Execution Time", "exec_time", ".2f", "minutes", divisor=60, higher_better=False)

    time_to_threshold.Plot()

    time_to_threshold.MigThresholdOverTime()
    time_to_threshold.MigTimeToThreshold()
    time_to_threshold.MigTimeToThreshold(speed=True)

    for mig_type in ["full", "7g.40gb"]: # "1g.5gb", "2g.10gb", "3g.20gb",
        time_to_threshold.MigThresholdOverTime(mig_type)
        time_to_threshold.MigTimeToThreshold(mig_type)
        time_to_threshold.MigTimeToThreshold(mig_type, speed=True)

    METRICS = {
        'DCGM_FI_PROF_GR_ENGINE_ACTIVE': "% of the of the graphic engine active",
        'DCGM_FI_PROF_DRAM_ACTIVE': "% of cycles the memory is active (tx/rx)",
        'DCGM_FI_DEV_POWER_USAGE': "Watt",
    }
    for metric, y_title in METRICS.items():
        prom_overview.Plot(metric=metric, y_title=y_title)
        report.PrometheusMultiGPUReport(metric)

    report.OverviewReport()
