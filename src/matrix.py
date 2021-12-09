import os, types, itertools, datetime, sys
import subprocess
import uuid

import common

class Matrix():
    def __init__(self, mode, yaml_desc):
        self.yaml_desc = yaml_desc
        self.mode = mode

    def run(self, exe):
        exe.expe_cnt = types.SimpleNamespace()
        exe.expe_cnt.total = 0
        exe.expe_cnt.current_idx = 0
        exe.expe_cnt.executed = 0
        exe.expe_cnt.recorded = 0
        exe.expe_cnt.errors = 0

        expe_ran = []
        for expe in self.yaml_desc['expe_to_run']:
            if not expe or expe.startswith("_"):
                exe.log(f"Skip disabled expe '{expe}'")
                continue

            stop = self.do_run_expe(exe, expe)
            if stop: break
            expe_ran.append(expe)

        exe.log(f"Ran {len(expe_ran)} {'matrices' if len(expe_ran) > 1 else 'matrix'}:", ", ".join(expe_ran))
        exe.log(f"Out of {exe.expe_cnt.total} experiments configured:")
        if exe.dry:
            exe.log(f"- {exe.expe_cnt.executed} would have been executed,")
        else:
            exe.log(f"- {exe.expe_cnt.executed} {'has' if exe.expe_cnt.executed == 1 else 'have' } been executed,")
        exe.log(f"- {exe.expe_cnt.recorded} {'was' if exe.expe_cnt.recorded == 1 else 'were'} already recorded,")
        exe.log(f"- {exe.expe_cnt.errors} failed.")

    def do_run_expe(self, exe, expe):
        exe.log("setup()")

        try:
            yaml_expe = self.yaml_desc['expe'][expe]
        except KeyError as e:
            exe.log(f"ERROR: Cannot run '{expe}': expe matrix not defined.")
            raise e

        if not isinstance(yaml_expe, dict):
            raise RuntimeError(f"Expe '{expe}' content should be a mapping ...")

        context = types.SimpleNamespace()
        context.params = types.SimpleNamespace()

        context.expe = expe
        context.expe_dir = f"{common.RESULTS_PATH}/{self.mode}/{context.expe}"
        context.path_tpl = self.yaml_desc['path_tpl']
        context.remote_mode = self.yaml_desc.get('remote_mode', False)
        context.script_tpl = self.yaml_desc['script_tpl']
        context.stop_on_error = self.yaml_desc.get('stop_on_error', False)
        context.common_settings = self.yaml_desc['common_settings']

        if context.remote_mode:
            print(f"""#! /bin/bash

set -x

if ! [[ -d "$1" ]]; then
  echo "FATAL: \$1 should be a result directory"
  exit 1
fi
RESULTS_DIR="$(realpath "$1")"

if ! [[ -d "$2" ]]; then
  echo "FATAL: \$2 should be MatrixBenchmark directory "
  exit 1
fi
MATRIX_BENCHMARK_DIR="$(realpath "$2")"
""", file=sys.stderr)

        settings = dict(context.common_settings)
        settings.update(yaml_expe)

        all_settings_items = [
            [(name, value) for value in (values if isinstance(values, list) else str(values).split(", "))]
            for name, values in settings.items()
        ]

        exe.expe_cnt.total += sum(1 for _ in itertools.product(*all_settings_items))

        # do fail in drymode if we cannot create the directories
        os.makedirs(context.expe_dir, exist_ok=True)

        stop = self.do_run_matrix(exe, all_settings_items, context, yaml_expe)
        if stop: return stop

        exe.log("#")
        exe.log(f"# Finished with '{context.expe}'")
        exe.log("#\n")

        return False

    def do_run_matrix(self, exe, all_settings_items, context, yaml_expe):
        for settings_items in itertools.product(*all_settings_items):
            settings = dict(settings_items)
            settings['expe'] = context.expe
            exe.expe_cnt.current_idx += 1

            if "extra" in settings:
                extra = settings["extra"]
                del settings["extra"]

                for kv in extra.split(", "):
                    if "=" not in kv:
                        raise ValueError(f"Invalid 'extra' setting: '{extra}' ('{kv}' has no '=')")
                    k, v = kv.split("=")
                    settings[k] = v

            key = common.Matrix.settings_to_key(settings)

            if key in common.Matrix.processed_map or key in common.Matrix.import_map:
                exe.log(f"experiment {exe.expe_cnt.current_idx}/{exe.expe_cnt.total} already recorded, skipping")
                if key in common.Matrix.processed_map:
                    exe.log(">", common.Matrix.processed_map[key].location.replace(common.RESULTS_PATH+f"/{self.mode}/", ''))
                else:
                    exe.log(">", common.Matrix.import_map[key].location.replace(common.RESULTS_PATH+f"/{self.mode}/", ''))
                exe.expe_cnt.recorded += 1
                continue

            bench_common_path = context.path_tpl.format(**settings)

            bench_uid = datetime.datetime.today().strftime("%Y%m%d_%H%M") + f".{uuid.uuid4().hex[:4]}"

            context.bench_dir = f"{context.expe}/{bench_common_path}{bench_uid}"
            context.bench_fullpath = f"{context.expe_dir}/{bench_common_path}{bench_uid}"

            if not exe.dry:
                os.makedirs(context.bench_fullpath)
            exe.log("---"*5)
            exe.log("")
            exe.log("")

            exe.log(f"running {exe.expe_cnt.current_idx}/{exe.expe_cnt.total}")
            for k, v in settings.items():
                exe.log(f"    {k}: {v}")
            try:
                ret = self.execute_benchmark(settings, context, exe)
            except KeyboardInterrupt:
                print("Stopping on keyboard interrupt.")
                return True

            if ret != None and not ret:
                exe.expe_cnt.errors += 1
                if context.stop_on_error:
                    print("Stopping on error.")
                    return True

            exe.expe_cnt.executed += 1
        return False

    def execute_benchmark(self, settings, context, exe):
        if not exe.dry:
            with open(f"{context.bench_fullpath}/settings", "w") as f:
                for k, v in settings.items():
                    if k == "expe": continue

                    print(f"{k}={v}", file=f)
                print(f"", file=f)

        settings_str = ""
        for k, v in settings.items():
            kv = f"{k}={v}"
            settings_str += f" '{kv}'" if " " in kv else f" {kv}"

        script = context.script_tpl.format(**settings)

        cmd = f"{script} {settings_str} 1> >(tee stdout) 2> >(tee stderr >&2)"
        cmd_fullpath = os.path.realpath(os.getcwd()+'/../') + cmd

        if exe.dry:
            exe.log(f"""\n
Results: {context.bench_fullpath.replace(common.RESULTS_PATH+'/', '')}
Command: {script}{settings_str}
---
""")

            return None
        elif context.remote_mode:

            print(f"""
CURRENT_DIRNAME="${{RESULTS_DIR}}/{context.bench_dir}"
mkdir -p "$CURRENT_DIRNAME"

if [[ "$(cat "$CURRENT_DIRNAME/exit_code")" != 0 ]]; then
  cd "$CURRENT_DIRNAME"
  ${{MATRIX_BENCHMARK_DIR}}/{cmd}
  echo "$?" > ./exit_code
else
  echo "Already recorded."
fi
""", file=sys.stderr)
            return None

        # no need to check here if ./exit_code exists and == 0,
        # we wouldn't reach this step if it did
        # (whereas the remote_mode generated script can be executed multiple times)

        exe.log(f"cd {context.bench_fullpath}")
        exe.log(cmd_fullpath)
        try:
            proc = subprocess.run(cmd_fullpath, cwd=context.bench_fullpath, shell=True, executable='/bin/bash')
        except KeyboardInterrupt as e:
            print("")
            exe.log("KeyboardInterrupt registered.")
            raise e

        exe.log(f"exit code: {proc.returncode}")
        # ^^^ blocks until the process terminates
        with open(f"{context.bench_fullpath}/exit_code", "w") as f:
            print(f"{proc.returncode}", file=f)

        return proc.returncode == 0
