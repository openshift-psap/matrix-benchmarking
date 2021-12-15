import os, sys

import matrix_view
import matrix_view.table_stats
import matrix_view.web
import matrix
import store
import common


def main():
    mode = store.parse_argv(sys.argv[1:])

    try:
        store_plugin = store.mode_store(mode)
    except Exception as e:
        print(f"FATAL: Could not load store_plugin for '{mode}': {e}")
        raise e

    print(f"Parsing {mode} data ...")

    store_plugin.parse_data(mode)
    print(f"Parsing {mode} data ... done")

    print(f"Found {len(common.Matrix.processed_map)} results")

    try:
        matrix_view.configure(store, mode)
    except Exception as e:
        print(f"FATAL: Failed to configure '{mode}' matrix_view: {e}")
        raise e

    matrix_view.table_stats.register_all()

    matrix_view.web.run(store_plugin, mode)

    return 0


if __name__ == "__main__":
    sys.exit(main())
