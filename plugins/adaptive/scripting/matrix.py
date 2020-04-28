import itertools, functools, operator
import datetime, os, atexit
import types

import dash_html_components as html

from ui import script
from ui import matrix_view

do_at_exit = {}
def exit_cleanup():
    if not do_at_exit:
        return

    print("scripts: do exit cleanups for", ", ".join(map(str, do_at_exit)))

    print(f"\n# Running {len(do_at_exit)} matrix scripts exit cleanups\n")

    for key, cleanup in list(do_at_exit.items()):
        print(f"scripts: cleaning up for '{key}' ...")
        try: cleanup()
        except Exception as e: print(e)

class AdaptiveMatrix():

    @staticmethod
    def add_custom_properties(yaml_desc, params):
        params.record_time = f"{yaml_desc['record_time']}s"

    @staticmethod
    def get_path_properties(yaml_expe):
        return ["record_time"] + sorted(yaml_expe.get('scripts') or [])

    @staticmethod
    def prepare_new_record(exe, context, settings_dict):
        exe.reset()
        exe.apply_settings(context.params.driver, settings_dict)

        exe.wait(10)

        exe.clear_record()
        exe.clear_quality()
        exe.wait(2)

        exe.request("share_pipeline", client=True, agent=True)
        exe.apply_settings("share_encoding", {})
        exe.apply_settings("share_resolution", {})
        exe.wait(1)

    @staticmethod
    def wait_end_of_recording(exe, yaml_desc):
        exe.wait(int(yaml_desc["record_time"]))

customized_matrix = AdaptiveMatrix


class Matrix(script.Script):

    def do_scripts_setup(self, exe, script_items, context):
        def do_setup(key, action, value):
            if isinstance(value, tuple): value = value[1]

            for cmd in self.yaml_desc['scripts'][key][action]:
                if value: cmd = cmd.replace(f"${key}", value)
                if "$" in cmd: import pdb;pdb.set_trace()
                exe.execute(cmd)

        for key, new_value in script_items:
            current_value = getattr(context.params, key)

            new_name = new_value
            try: new_value = self.yaml_desc['script_config'][key][new_value]
            except KeyError: pass

            if current_value == new_value: continue

            if current_value:
                exe.log(f"teardown({key})")

                do_at_exit[key]()
                del do_at_exit[key]

            if new_value:
                exe.log(f"setup({key}, {new_value})")
                do_setup(key, "before", new_value)

                def at_exit(_key, _new_value):
                    do_setup(_key, "after", _new_value)

                import functools # otherwise key/new_value arrive wrong in `at_exit`
                do_at_exit[key] = functools.partial(at_exit, key, new_value)

            setattr(context.params, key, new_name)


    def do_run_the_settings_matrix(self, exe, settings_matrix, context, yaml_expe):
        def scripted_property_to_named_value(key):
            val = context.params.__dict__[key]
            return val[0] if isinstance(val, tuple) else val
        def param_to_named_value(key):
            val = context.params.__dict__[key]
            return val[0] if isinstance(val, tuple) else val

        path_properties = customized_matrix.get_path_properties(yaml_expe)
        file_path = "/".join(scripted_property_to_named_value(key) for key in path_properties)

        fix_key = "_".join(f"{key}={param_to_named_value(key)}".replace("_", "-")
                           for key in sorted(context.params.__dict__))

        os.makedirs(f"{context.expe_dir}/{file_path}/", exist_ok=True)

        for settings_items in itertools.product(*settings_matrix):
            settings_dict = dict(settings_items)

            settings_str = ";".join([f"{k}={v}" for k, v in settings_items])

            current_key = settings_str.replace(';', "_")

            file_entry = " | ".join([fix_key, file_path, current_key])
            file_key = "_".join([fix_key, current_key])

            exe.expe_cnt.current_idx += 1

            exe.log("---")
            exe.log(f"running {exe.expe_cnt.current_idx}/{exe.expe_cnt.total}")
            exe.log("> "+file_key)

            key = f"experiment={context.expe.replace('_', '-')}_{file_key}"
            try: previous_entry = matrix_view.Matrix.entry_map[key]
            except KeyError: pass # no previous entry, run!
            else:
                exe.log(f">> already recorded, skipping | {previous_entry.filename}")
                continue

            customized_matrix.prepare_new_record(exe, context, settings_dict)

            for k in context.params.__dict__:
                exe.append_quality(f"{k}: {scripted_property_to_named_value(k)}")

            exe.append_quality(f"settings: {settings_str}")

            customized_matrix.wait_end_of_recording(exe, yaml_expe)

            exe.expe_cnt.executed += 1

            dest = f"{context.expe_dir}/{file_path}/{current_key}.rec"

            exe.save_record(dest)

            exe.log(f"write result: {context.results_filename} << {file_entry}")

            if exe.dry: continue

            with open(context.results_filename, "a") as f:
                print(file_entry, file=f)

    def do_run(self, exe):
        exe.expe_cnt = types.SimpleNamespace()
        exe.expe_cnt.total = 0
        exe.expe_cnt.current_idx = 0
        exe.expe_cnt.executed = 0

        expe_ran = []
        for expe in self.yaml_desc['run']:
            if not expe or expe.startswith("_"):
                exe.log(f"Skip disabled expe '{expe}'")
                continue

            self.do_run_expe(exe, expe)
            expe_ran.append(expe)

        exe.log(f"Ran {len(expe_ran)} expe:", ", ".join(expe_ran))
        exe.log(f"Performed {exe.expe_cnt.executed}/{exe.expe_cnt.total} experiments.")

        exe.log(f"Skipped {exe.expe_cnt.total - exe.expe_cnt.executed} "
                "experiments already recorded.")

    def do_run_expe(self, exe, expe):
        exe.log("setup()")
        for cmd in (self.yaml_desc.get('scripts', {}).get("setup") or []):
            exe.execute(cmd)

        def teardown():
            for cmd in (self.yaml_desc.get('scripts', {}).get("teardown") or []):
                exe.execute(cmd)

        do_at_exit["__benchmark__"] = teardown

        try:
            yaml_expe = self.yaml_desc['expe'][expe]
        except KeyError as e:
            exe.log(f"ERROR: Cannot run '{expe}': expe matrix not defined.")
            raise e

        context = types.SimpleNamespace()
        context.params = types.SimpleNamespace()
        context.params.driver = yaml_expe["driver"]

        for script_propery in (yaml_expe.get("scripts") or []):
            context.params.__dict__[script_propery] = None

        customized_matrix.add_custom_properties(self.yaml_desc, context.params)

        settings_matrix = [[(name, value) for value in str(values).split(", ")]
                           for name, values in (yaml_expe.get("settings") or {}).items()]

        def values_to_list(values):
            return (values.items() if isinstance(values, dict)
                    else str(values).split(", "))

        script_matrix = [[(name, value) for value in values_to_list(values)]
                         for name, values in (yaml_expe.get("scripts") or {}).items()]

        nb_settings_params_expe = sum(1 for _ in itertools.product(*settings_matrix))
        nb_script_expe = sum(1 for _ in itertools.product(*script_matrix))
        exe.expe_cnt.total += nb_script_expe * nb_settings_params_expe

        context.expe = expe
        context.script_name = self.yaml_desc["name"]
        context.expe_dir = f"{script.RESULTS_PATH}/{context.expe}"
        context.results_filename = f"{context.expe_dir}/{context.script_name}.csv"

        exe.log("Loading previous matrix results from", context.results_filename)


        matrix_view.parse_data(context.results_filename, reloading=True)
        exe.log("Loading previous matrix results: done")

        # do fail in drymode if we cannot create the directories
        os.makedirs(context.expe_dir, exist_ok=True)

        if not exe.dry:
            with open(context.results_filename, "a") as f:
                print(f"# {datetime.datetime.now()}", file=f)

        for script_items in itertools.product(*script_matrix):
            exe.reset()
            self.do_scripts_setup(exe, script_items, context)
            try:
                self.do_run_the_settings_matrix(exe, settings_matrix, context, yaml_expe)
            except KeyboardInterrupt:
                print("Interrupted ...")
                break

        self.do_scripts_setup(exe, [(k, None) for k, v in script_items], context)
        exe.log("teardown()")
        teardown()
        del do_at_exit["__benchmark__"]

        exe.log("#")
        exe.log(f"# Finished with {context.expe}")
        exe.log("#")

def configure(expe):
    atexit.register(exit_cleanup)
