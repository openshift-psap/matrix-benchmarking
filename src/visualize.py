import os, sys
import importlib

import matrix_view
import matrix_view.table_stats
import matrix_view.web
import matrix
import store
import common

DEFAULT_MODE = "specfem"
def main():
    for expe_filter in sys.argv[1:]:
        key, _, value = expe_filter.partition("=") if "=" in expe_filter \
            else ("expe", True, expe_filter)

        store.experiment_filter[key] = value

    mode = store.experiment_filter.get("mode", DEFAULT_MODE)

    print(f"Loading {mode} storage module ...")
    store_pkg_name = f"store.{mode}"
    store_plugin = importlib.import_module(store_pkg_name)

    print(f"Parsing {mode} data ...")
    store_plugin.parse_data(mode)
    print(f"Parsing {mode} data ... done")

    print(f"Found {len(common.Matrix.processed_map)} results")

    matrix_view.configure(store, mode)
    matrix_view.table_stats.register_all()

    matrix_view.web.run(store_plugin, mode)

    return 0


if __name__ == "__main__":
    sys.exit(main())
