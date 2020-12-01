import matrix_view.mpi_benchmark.osu
import matrix_view.table_stats
from common import Matrix
def register():
    matrix_view.mpi_benchmark.osu.SimpleNet()
    matrix_view.table_stats.TableStats.Value(
        id_name="sysbench-cpu",
        name="Sysbench CPU",
        field="cpu_evt_per_sec",
        fmt="%d evt/seconds",
        unit="Events per seconds",
        higher_better=True,
    )

    matrix_view.table_stats.TableStats.Value(
        id_name="sysbench-fio",
        name="Sysbench FIO Write",
        field="fio_thput_write",
        fmt="%d MiB/s",
        unit="MiB per seconds",
        higher_better=True,
    )
    matrix_view.table_stats.TableStats.Value(
        id_name="sysbench-fio",
        name="Sysbench FIO Read",
        field="fio_thput_read",
        fmt="%d MiB/s",
        unit="MiB per seconds",
        higher_better=True,
    )
