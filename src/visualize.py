import os, sys
import importlib

import matrix_view
import matrix_view.table_stats
import matrix_view.web
import matrix
import store
import common

def main():
    mode = "mpi_benchmark"

    store_pkg_name = f"store.{mode}"
    store_plugin = importlib.import_module(store_pkg_name)

    print(f"Parsing {mode} data ...")

    try: expe_filter = sys.argv[1]
    except IndexError: expe_filter = None

    store_plugin.parse_data(mode, expe_filter)
    print(f"Parsing {mode} data ... done")

    print(f"Found {len(common.Matrix.processed_map)} results")

    matrix_view.configure(store, mode)
    matrix_view.table_stats.register_all()
    import pdb;pdb.set_trace()
    matrix_view.web.run(store_plugin, mode)

    return 0


if __name__ == "__main__":
    sys.exit(main())
