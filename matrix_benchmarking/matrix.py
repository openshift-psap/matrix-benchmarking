import os, types, itertools, datetime, sys
import subprocess
import uuid
import logging
import pathlib

import yaml

import matrix_benchmarking
import matrix_benchmarking.common as common
import matrix_benchmarking.store as store
import matrix_benchmarking.cli_args as cli_args

class Matrix():
    def __init__(self, yaml_desc):
        self.yaml_desc = yaml_desc

    def run(self,):
        tracker = types.SimpleNamespace()
        tracker.expe_cnt = types.SimpleNamespace()
        tracker.expe_cnt.total = 0
        tracker.expe_cnt.current_idx = 0
        tracker.expe_cnt.executed = 0
        tracker.expe_cnt.recorded = 0
        tracker.expe_cnt.errors = 0
        tracker.dry = not cli_args.kwargs["run"]

        expe_ran = []

        expe_to_run = cli_args.kwargs["expe_to_run"]
        if isinstance(expe_to_run, str):
            expe_to_run = expe_to_run.split(",")

        for expe in expe_to_run:
            if not expe or expe.startswith("_"):
                logging.info(f"Skip disabled expe '{expe}'")
                continue

            stop = self.do_run_expe(tracker, expe)
            if stop: break
            expe_ran.append(expe)

        logging.info(f"Ran {len(expe_ran)} {'matrices' if len(expe_ran) > 1 else 'matrix'}: {', '.join(expe_ran)}")
        logging.info(f"Out of {tracker.expe_cnt.total} experiments configured:")
        if tracker.dry:
            logging.info(f"- {tracker.expe_cnt.executed} would have been executed,")
        else:
            logging.info(f"- {tracker.expe_cnt.executed} {'has' if tracker.expe_cnt.executed == 1 else 'have' } been executed,")
        logging.info(f"- {tracker.expe_cnt.recorded} {'was' if tracker.expe_cnt.recorded == 1 else 'were'} already recorded,")
        logging.info(f"- {tracker.expe_cnt.errors} failed.")

        return tracker.expe_cnt.errors

    def do_run_expe(self, tracker, expe):
        logging.info("setup()")

        try:
            yaml_expe = self.yaml_desc['expe'][expe]
        except KeyError as e:
            logging.error(f"Cannot run experiment '{expe}': experiment matrix not defined.")
            return True

        if not isinstance(yaml_expe, dict):
            raise RuntimeError(f"Expe '{expe}' content should be a mapping ...")

        context = types.SimpleNamespace()
        context.settings = types.SimpleNamespace()

        context.expe = expe
        context.expe_dir = pathlib.Path(".") / cli_args.kwargs["results_dirname"] / context.expe

        context.path_tpl = cli_args.kwargs["path_tpl"]
        context.script_tpl = cli_args.kwargs["script_tpl"]
        context.remote_mode = cli_args.kwargs["remote_mode"]
        context.stop_on_error = cli_args.kwargs["stop_on_error"]

        context.common_settings = self.yaml_desc.get('common_settings', {})

        if not tracker.dry and context.remote_mode and tracker.expe_cnt.current_idx == 0:
            print(f"""#! /bin/bash

set -x

if ! [[ -d "$1" ]]; then
  echo "FATAL: \$1 should point to the result directory"
  exit 1
fi
RESULTS_DIR="$(realpath "$1")"

if ! [[ -d "$2" ]]; then
  echo "FATAL: \$2 should point to 'exec' directory "
  exit 1
fi
EXEC_DIR="$(realpath "$2")"
""", file=sys.stderr)

        settings = dict(context.common_settings or {})
        settings.update(yaml_expe)

        all_settings_items = [
            [(name, value) for value in (values if isinstance(values, list) else [values])]
            for name, values in settings.items()
        ]

        tracker.expe_cnt.total += sum(1 for _ in itertools.product(*all_settings_items))

        if not tracker.dry and not context.remote_mode:
            os.makedirs(context.expe_dir, exist_ok=True)

        stop = self.do_run_matrix(tracker, all_settings_items, context, yaml_expe)
        if stop: return stop

        logging.info("#")
        logging.info(f"# Finished with '{context.expe}'")
        logging.info("#")
        logging.info("")

        return False

    def do_run_matrix(self, tracker, all_settings_items, context, yaml_expe):
        for settings_items in itertools.product(*all_settings_items):
            settings = dict(settings_items)

            tracker.expe_cnt.current_idx += 1

            path_tpl = context.path_tpl
            expe_path_tpl = settings.get("--path-tpl")
            if expe_path_tpl:
                del settings["--path-tpl"]
                path_tpl = expe_path_tpl

            if path_tpl is None:
                raise ValueError("<top-level>.--path-tpl or <top-level>.expe[<expe>].--path-tpl must be provided.")

            if "extra" in settings:
                extra = settings["extra"]
                del settings["extra"]
                if isinstance(extra, dict):
                    raise ValueError(f"'extra' is a dict, does it contain a ':'? ({extra})")
                for kv in extra.split(", "):
                    if "=" not in kv:
                        raise ValueError(f"Invalid 'extra' setting: '{extra}' ('{kv}' has no '=')")
                    k, v = kv.split("=")
                    settings[k.strip()] = v.strip()

            key = common.Matrix.settings_to_key(settings)

            if key in common.Matrix.processed_map or key in common.Matrix.import_map:
                logging.info(f"experiment {tracker.expe_cnt.current_idx}/{tracker.expe_cnt.total} already recorded, skipping.")
                location =  common.Matrix.processed_map[key].location if key in common.Matrix.processed_map \
                    else common.Matrix.import_map[key].location

                logging.info(f"> {location.relative_to(context.expe_dir.parent)}")
                logging.info("")
                tracker.expe_cnt.recorded += 1
                continue

            try:
                bench_common_path = path_tpl.format(**settings, settings=settings)
            except KeyError as e:
                logging.error(f"cannot apply the path template '{path_tpl}': key '{e.args[0]}' missing from {settings}")
                tracker.expe_cnt.errors += 1
                if context.stop_on_error:
                    return True
                continue

            bench_uid = datetime.datetime.today().strftime("%Y%m%d_%H%M") + f".{uuid.uuid4().hex[:4]}"

            context.bench_dir = pathlib.Path(context.expe) / f"{bench_common_path}{bench_uid}"
            context.bench_fullpath = context.expe_dir / f"{bench_common_path}{bench_uid}"

            if not tracker.dry and not context.remote_mode:
                os.makedirs(context.bench_fullpath)

            logging.info("---"*5)
            logging.info("")
            logging.info("")

            logging.info(f"running {tracker.expe_cnt.current_idx}/{tracker.expe_cnt.total}")
            for k, v in settings.items():
                logging.info(f"    {k}: {v}")
            try:
                ret = self.execute_benchmark(settings, context, tracker)
            except KeyboardInterrupt:
                logging.error("Stopping on keyboard interrupt.")
                return True

            if ret != None and not ret:
                tracker.expe_cnt.errors += 1
                if context.stop_on_error:
                    logging.warning("Stopping on error.")
                    return True

            tracker.expe_cnt.executed += 1
        return False

    def execute_benchmark(self, settings, context, tracker):
        if not tracker.dry and not context.remote_mode:
            with open(context.bench_fullpath / "settings.yaml", "w") as out_f:
                yaml.dump(settings, out_f)

            for test_file, _content in self.yaml_desc.get("test_files", {}).items():
                content = _content if isinstance(_content, str) else \
                    yaml.dump(_content, default_flow_style=False, sort_keys=False)

                with open(context.bench_fullpath / test_file, "w") as f:
                    print(content, file=f)

        try:
            script = context.script_tpl.format(**settings)
        except KeyError as e:
            logging.error(f"cannot apply the script template '{context.script_tpl}': key '{e.args[0]}' missing from {settings}")
            tracker.expe_cnt.errors += 1
            if context.stop_on_error:
                return False

            return None

        cmd_fullpath = f"{pathlib.Path(os.getcwd()) / script} 1> >(tee stdout) 2> >(tee stderr >&2)"

        if tracker.dry:
            try:
                results_dir = context.bench_fullpath.relative_to(context.expe_dir.parent.parent)
            except ValueError: # (fullpath )is not in the subpath of (expe_dir)
                results_dir = context.expe_dir

            logging.info(f"""\n
Results: {results_dir}
Command: {script}
---
""")

            return None
        elif context.remote_mode:
            settings_str = yaml.dump(settings)
            print(f"""
echo "Expe {tracker.expe_cnt.current_idx}/{tracker.expe_cnt.total}"
CURRENT_DIRNAME="${{RESULTS_DIR}}/{context.bench_dir}"

if [[ "$(cat "$CURRENT_DIRNAME/exit_code" 2>/dev/null)" != 0 ]]; then
  mkdir -p "$CURRENT_DIRNAME"
  cd "$CURRENT_DIRNAME"
  [[ "$$CURRENT_DIRNAME" ]] && rm -rf -- "$CURRENT_DIRNAME"/*
  echo -e "{settings_str}" > ./settings.yaml
  echo "$(date) Running expe {tracker.expe_cnt.current_idx}/{tracker.expe_cnt.total}"
  ${{EXEC_DIR}}/{script}
  echo "$?" > ./exit_code
else
  echo "Already recorded in $CURRENT_DIRNAME."
fi
""", file=sys.stderr)
            return None

        # no need to check here if ./exit_code exists and == 0,
        # we wouldn't reach this step if it did
        # (whereas the remote_mode generated script can be executed multiple times)

        logging.info(f"cd {context.bench_fullpath}")
        logging.info(cmd_fullpath)
        try:
            proc = subprocess.run(cmd_fullpath, cwd=context.bench_fullpath, shell=True,
                                  stdin=subprocess.PIPE,
                                  executable='/bin/bash')
        except KeyboardInterrupt as e:
            logging.info("")
            logging.info("KeyboardInterrupt registered.")
            raise e

        ret = proc.returncode
        # /!\ ^^^^^^^^^^^^^^^ blocks until the process terminates

        logging.info(f"exit code: {ret}")
        with open(context.bench_fullpath / "exit_code", "w") as out_f:
            print(f"{ret}", file=out_f)

        return ret == 0
