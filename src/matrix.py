import os, types, itertools, datetime

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
        for expe in self.yaml_desc['run']:
            if not expe or expe.startswith("_"):
                exe.log(f"Skip disabled expe '{expe}'")
                continue

            self.do_run_expe(exe, expe)
            expe_ran.append(expe)

        exe.log(f"Ran {len(expe_ran)} matri{'ces' if len(expe_ran) > 1 else 'x'}:", ", ".join(expe_ran))
        exe.log(f"Out of {exe.expe_cnt.total} experiments configured:")
        if exe.dry:
            exe.log(f"- {exe.expe_cnt.executed} would have been executed,")
        else:
            exe.log(f"- {exe.expe_cnt.executed} have been executed,")
        exe.log(f"- {exe.expe_cnt.recorded} were already recorded,")
        exe.log(f"- {exe.expe_cnt.errors} failed.")

    def do_run_expe(self, exe, expe):
        exe.log("setup()")

        try:
            yaml_expe = self.yaml_desc['expe'][expe]
        except KeyError as e:
            exe.log(f"ERROR: Cannot run '{expe}': expe matrix not defined.")
            raise e

        context = types.SimpleNamespace()
        context.params = types.SimpleNamespace()

        all_settings_items = [[(name, value) for value in (values if isinstance(values, list) else str(values).split(", "))]
                    for name, values in (yaml_expe.get("settings") or {}).items()]

        exe.expe_cnt.total += sum(1 for _ in itertools.product(*all_settings_items))

        context.expe = expe
        context.expe_dir = f"{common.RESULTS_PATH}/{self.mode}/{context.expe}"
        context.path_fmt = self.yaml_desc['path_fmt']

        # do fail in drymode if we cannot create the directories
        os.makedirs(context.expe_dir, exist_ok=True)

        if not exe.dry:
            with open(context.results_filename, "a") as f:
                print(f"# {datetime.datetime.now()}", file=f)

        self.do_run_matrix(exe, all_settings_items, context, yaml_expe)

        exe.log("#")
        exe.log(f"# Finished with '{context.expe}'")
        exe.log("#")

    def do_run_matrix(self, exe, all_settings_items, context, yaml_expe):
        for settings_items in itertools.product(*all_settings_items):
            settings = dict(settings_items)
            settings['expe'] = context.expe

            if "extra" in settings:
                extra = settings["extra"]
                del settings["extra"]

                for kv in extra.split(", "):
                    k, v = kv.split("=")
                    settings[k] = v

            key = common.Matrix.settings_to_key(settings)

            if key in common.Matrix.processed_map:
                print("INFO: experiment already recorded, skipping")
                print("INFO: >", common.Matrix.processed_map[key][1].replace(common.RESULTS_PATH+f"/{self.mode}/", ''))
                exe.expe_cnt.recorded += 1
                continue

            bench_common_path = context.path_fmt.format(**settings)
            bench_uid = datetime.datetime.today().strftime("%Y%m%d_%H%M%S_%f")
            bench_fullpath = f"{context.expe_dir}/{bench_common_path}{bench_uid}"

            os.makedirs(bench_fullpath)

            exe.expe_cnt.current_idx += 1

            exe.log("---")
            exe.log(f"running {exe.expe_cnt.current_idx}/{exe.expe_cnt.total}")

            self.execute_benchmark(bench_fullpath, settings)

            exe.expe_cnt.executed += 1

    def execute_benchmark(self, bench_fullpath, settings):
        with open(f"{bench_fullpath}/settings", "w") as f:
            for k, v in settings.items():
                print(f"{k}={v}", file=f)
            print(f"", file=f)

        print(" ".join(f"{k}={v}" for k, v in settings.items()))

        pass
