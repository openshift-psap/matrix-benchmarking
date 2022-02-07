import os, sys

import matrix_view
import matrix_view.table_stats
import matrix_view.web
import matrix
import store
import common


def main():
    benchmark_name = store.parse_argv(sys.argv[1:])

    try:
        workload_store = store.load_store()
    except Exception as e:
        print(f"FATAL: Could not load workload store module: {e}")
        raise e

    print(f"Parsing results results ...")

    workload_store.parse_data(benchmark_name)
    print(f"Parsing {benchmark_name} results ... done")

    print(f"Found {len(common.Matrix.processed_map)} results")

    try:
        matrix_view.configure(store)
    except Exception as e:
        print(f"FATAL: Failed to configure the plotting module: {e}")
        raise e

    matrix_view.table_stats.register_all()

    matrix_view.web.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
