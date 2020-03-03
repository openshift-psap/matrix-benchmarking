import dash_html_components as html
import datetime
import os
import itertools, functools, operator
import types
import atexit

from . import script
from . import matrix_view

RESULTS_PATH = os.path.realpath(os.path.dirname(os.path.realpath(__file__)) + "/../../results")

class SimpleScript(script.Script):
    def to_html(self):
        def prop_to_html(key):
            yield html.P([html.B(key+": "), html.I(self.yaml_desc.get(key, "[missing]"))])

        def keylist_to_html(key, yaml_desc=self.yaml_desc):
            if not key in yaml_desc: return

            yield html.P(html.B(key+": "))
            lst = [html.Li(e) for e in yaml_desc[key]]

            yield html.Ul(lst)

        def run_to_html():
            yield html.P(html.B("run: "))
            if not "run" in self.yaml_desc or self.yaml_desc["run"] is None:
                yield "nothing to run"
                return
            yaml_run = self.yaml_desc["run"]

            codecs = []
            for test_name, test_params in yaml_run.items():
                params = []

                for param_name, param_values in test_params.items():
                    if param_name.startswith("_"):
                        param_tag = html.B(param_name[1:])
                    else:
                        param_tag = param_name

                    params += [html.Li([param_tag, ": ", param_values])]

                codecs += [html.Li([html.I(test_name), html.Ul(params)])]

            yield html.Ul(codecs)

        yield from prop_to_html("description")
        yield from keylist_to_html("before")
        yield from run_to_html()
        yield from prop_to_html("record_time")
        yield from keylist_to_html("after")

        yield html.Br()

    def do_run(self, exe):
        codec_name = self.yaml_desc["codec"]
        record_time = int(self.yaml_desc["record_time"])

        first_record = True
        def init_recording(test_name):
            exe.wait(5)
            exe.clear_record()
            exe.clear_quality()
            exe.request("share_pipeline", client=True, agent=True)
            exe.set_encoding("share_encoding", {})
            exe.append_quality(f"!running: {self.name}")
            exe.append_quality(f"!running: {self.name} / {test_name}")
            exe.wait(1)

        for cmd in self.yaml_desc.get("before", []): exe.execute(cmd)

        exe.reset_encoder()

        for test_name, test_cfg in self.yaml_desc["run"].items():
            if test_cfg.get("_disabled", False):
                exe.log(f"{self.name} / {test_name}: disabled")
                continue

            if not first_record:
                exe.append_quality(f"!running: {self.name} / {test_name}")
            rolling_param  = None
            fixed_params = {}

            for param_name, param_value in test_cfg.items():
                if param_name.startswith("_"):
                    assert rolling_param is None
                    rolling_param = param_name[1:], param_value
                    continue

                fixed_params[param_name] = param_value

            first_test = True
            for rolling_param_value in rolling_param[1].split(", "):
                if first_test:
                    first_test = True

                    first_params = {**fixed_params, **{rolling_param[0]: rolling_param_value}}
                    exe.set_encoding(codec_name, first_params)

                    if first_record:
                        first_record = False

                        # this late initialization is necessary to
                        # ensure that the recording data are 100%
                        # clean: the first encoding config is already
                        # set, so no data from the previous
                        # configuration is recorded
                        init_recording(test_name)

                        exe.set_encoding(codec_name, first_params)
                else:
                    exe.set_encoding(codec_name, {rolling_param[0]: rolling_param_value})

                exe.wait(record_time)

            exe.reset_encoder()

        exe.append_quality(f"!finished: {self.name}")

        dest = "{RESULTS_PATH}/simple/" + self.to_id() + "_" + datetime.datetime.today().strftime("%Y%m%d-%H%M") + ".rec"
        exe.save_record(dest)

        for cmd in self.yaml_desc.get("after", []): exe.execute(cmd)

        exe.log("done!")

do_at_exit = {}
def exit_cleanup():
    if do_at_exit:
        print("scripts: do exit cleanups for", ", ".join(map(str, do_at_exit)))

    for key, cleanup in do_at_exit.items():
        print(f"scripts: cleaning up for '{key}' ...")
        try: cleanup()
        except Exception as e: print(e)

atexit.register(exit_cleanup)

class MatrixScript(script.Script):
    def to_html(self):
        def prop_to_html(key):
            yield html.P([html.B(key+": "), html.I(self.yaml_desc.get(key, "[missing]"))])

        def keylist_to_html(key, yaml_desc=self.yaml_desc):
            if not key in yaml_desc: return

            yield html.B(key+": ")
            lst = [html.Li(e) for e in yaml_desc[key]]

            yield html.Ul(lst)

        def scripts_to_html():
            yield html.P(html.B("scripts".upper()))

            scripts = []

            for key in self.yaml_desc["scripted_properties"]:
                elts = []
                for action in ["before", "after"]:
                    elts.append(html.Li([e for e in keylist_to_html(action, self.yaml_desc["scripts"][key])]))
                scripts.append(html.Li([html.B(f"{key}:"), html.Ul(elts)]))

            scripts += [html.Li([e for e in keylist_to_html(action, self.yaml_desc["scripts"])])
                       for action in ["setup", "teardown"]]
            yield html.Ul(scripts)

        def matrix_to_html(key):
            yield html.P(html.B(key+":"))

            params = []
            for param, values in self.yaml_desc[key].items():
                if isinstance(values, dict):
                    items = []
                    for name, value in values.items():
                        # TODO: test if there's http in value before making a link
                        items += [html.A(name, href=value), " | "]
                    if items: items.pop() # remove last |

                    params.append(html.Li([html.I(param), " → "] + items))
                else:
                    values = str(values)
                    params.append(html.Li([html.I(param.rpartition("=")[-1]), " → ",
                                           " | ".join(values.split(", "))]))
            yield html.Ul(params)

        yield from prop_to_html("name")
        yield from prop_to_html("record_time")
        yield from prop_to_html("codec")
        yield html.Hr()
        yield from matrix_to_html("matrix")
        yield from matrix_to_html("scripted_properties")
        yield html.Hr()
        yield from scripts_to_html()

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


    def do_run_the_streaming_matrix(self, exe, encoding_matrix, context, yaml_expe):
        def scripted_property_to_named_value(key):
            val = context.params.__dict__[key]
            return val[0] if isinstance(val, tuple) else val
        def param_to_named_value(key):
            val = context.params.__dict__[key]
            return val[0] if isinstance(val, tuple) else val

        path_properties = ["record_time"] + sorted(yaml_expe['scripts'])
        file_path = "/".join(scripted_property_to_named_value(key) for key in path_properties)

        fix_key = "_".join(f"{key}={param_to_named_value(key)}".replace("_", "-")
                           for key in sorted(context.params.__dict__))

        os.makedirs(f"{context.expe_dir}/{file_path}/", exist_ok=True)

        for encoding_items in itertools.product(*encoding_matrix):
            encoding_dict = dict(encoding_items)

            encoding_str = ";".join([f"{k}={v}" for k, v in encoding_items])
            encoding_str = encoding_str.replace('gst.prop=', '').replace('nv.', '')

            current_key = encoding_str.replace(';', "_")

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
                exe.expe_cnt.skipped += 1
                continue

            exe.reset_encoder()

            exe.set_encoding(context.params.codec, encoding_dict)
            exe.wait(10)
            exe.clear_record()
            exe.clear_quality()
            exe.wait(2)

            for k in context.params.__dict__:
                exe.append_quality(f"{k}: {scripted_property_to_named_value(k)}")

            exe.append_quality(f"encoding: {encoding_str}")

            exe.request("share_pipeline", client=True, agent=True)
            exe.set_encoding("share_encoding", {})
            exe.set_encoding("share_resolution", {})
            exe.wait(1)

            exe.wait(int(self.yaml_desc["record_time"]))

            dest = f"{context.expe_dir}/{file_path}/{current_key}.rec"

            exe.save_record(dest)

            exe.log(f"write result: {context.results_filename} << {file_entry}")

            if not exe.dry:
                print(file_entry, file=open(context.results_filename, "a"))

    def get_resolution(self, exe):
        from . import UIState
        import time
        # messages in db.quality are 'newer first'

        resolution = None
        db = UIState().DB

        # find the ts of the last quality message, if any
        # (UI quality messages may have ts=None)
        last_quality_ts = 0
        for ts, src, msg in db.quality[:]:
            if not ts: continue
            last_quality_ts = ts
            break

        exe.set_encoding("share_resolution", {}, force=True)
        MAX_WAIT_LOOPS = 5 # 2.5s
        nb_loops = 0

        while True:
            nb_loops += 1
            time.sleep(0.5)
            for ts, src, msg in db.quality[:]:
                if ts and ts <= last_quality_ts: break
                if not msg.startswith("resolution: "): continue
                # msg = 'guest: resolution: height=1919 width=1007'
                try: return dict([kv.split('=') for kv in msg.split()[1:]])
                except Exception as e:
                    print(f"Failed to parse resolution ({msg}):", e)
                    return None

            exe.log(f"resolution not found, attempt {nb_loops}/{MAX_WAIT_LOOPS}")
            if nb_loops >= MAX_WAIT_LOOPS:
                print("bye")
                return None

    def do_run(self, exe):
        exe.expe_cnt = types.SimpleNamespace()
        exe.expe_cnt.total = 0
        exe.expe_cnt.current_idx = 0
        exe.expe_cnt.skipped = 0

        expe_ran = []
        for expe in self.yaml_desc['run']:
            if not expe or expe.startswith("_"):
                exe.log(f"Skip disabled expe '{expe}'")
                continue

            self.do_run_expe(exe, expe)
            expe_ran.append(expe)

        exe.log(f"Ran {len(expe_ran)} expe:", ", ".join(expe_ran))
        exe.log(f"Performed {exe.expe_cnt.total - exe.expe_cnt.skipped}/{exe.expe_cnt.total} experiments.")
        exe.log(f"Skipped {exe.expe_cnt.skipped} experiments already recorded.")

    def do_run_expe(self, exe, expe):
        exe.log("setup()")
        for cmd in self.yaml_desc['scripts'].get("setup", []):
            exe.execute(cmd)

        def teardown():
            for cmd in self.yaml_desc['scripts'].get("teardown", []):
                exe.execute(cmd)
        do_at_exit["__vm"] = teardown

        try:
            yaml_expe = self.yaml_desc['expe'][expe]
        except KeyError as e:
            exe.log(f"ERROR: Cannot run '{expe}': expe matrix not defined.")
            raise e

        context = types.SimpleNamespace()
        context.params = types.SimpleNamespace()
        context.params.codec = yaml_expe["codec"]
        context.params.record_time = f"{self.yaml_desc['record_time']}s"

        for script_propery in yaml_expe["scripts"]:
            context.params.__dict__[script_propery] = None

        encoding_matrix = [[(name, value) for value in str(values).split(", ")]
                           for name, values in yaml_expe["encoding"].items()]

        def values_to_list(values):
            return (values.items() if isinstance(values, dict)
                    else str(values).split(", "))

        script_matrix = [[(name, value) for value in values_to_list(values)]
                         for name, values in yaml_expe["scripts"].items()]

        nb_encoding_params_expe = functools.reduce(operator.mul, map(len, encoding_matrix), 1)
        nb_script_expe = functools.reduce(operator.mul, map(len, script_matrix), 1)
        exe.expe_cnt.total += nb_script_expe * nb_encoding_params_expe

        context.expe = expe
        context.script_name = self.yaml_desc["name"]
        context.expe_dir = f"{RESULTS_PATH}/{context.expe}"
        context.results_filename = f"{context.expe_dir}/{context.script_name}.csv"

        exe.log("Loading previous matrix results from", context.results_filename)

        matrix_view.parse_data(context.results_filename, reloading=True)
        exe.log("Loading previous matrix results: done")

        # do fail in drymode if we cannot create the directories
        os.makedirs(context.expe_dir, exist_ok=True)

        if not exe.dry:
            print(f"# {datetime.datetime.now()}", file=open(context.results_filename, "a"))

        for script_items in itertools.product(*script_matrix):
            exe.reset_encoder()
            self.do_scripts_setup(exe, script_items, context)
            self.do_run_the_streaming_matrix(exe, encoding_matrix, context, yaml_expe)

        self.do_scripts_setup(exe, [(k, None) for k, v in script_items], context)
        exe.log("teardown()")
        teardown()
        del do_at_exit["__vm"]

        exe.log("#")
        exe.log(f"# Finished with {context.expe}")
        exe.log("#")

TYPES = {
    None: SimpleScript,
    "simple": SimpleScript,
    "matrix": MatrixScript,
}
