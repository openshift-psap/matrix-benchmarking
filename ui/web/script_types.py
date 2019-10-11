import dash_html_components as html
import datetime
import itertools, functools, operator

from . import script
from . import matrix_view

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
            exe.clear_graph()
            exe.clear_quality()
            exe.wait(1)
            exe.append_quality(f"!running: {self.name}")
            exe.wait(1)
            exe.append_quality(f"!running: {self.name} / {test_name}")
            exe.wait(1)

        for cmd in self.yaml_desc.get("before", []): exe.execute(cmd)

        exe.reset()

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

            exe.reset()
            exe.wait(5)

        exe.append_quality(f"!finished: {self.name}")

        dest = self.to_id() + "_" + datetime.datetime.today().strftime("%Y%m%d-%H%M") + ".rec"
        exe.save_graph(dest)

        for cmd in self.yaml_desc.get("after", []): exe.execute(cmd)

        exe.log("done!")

class MatrixScript(script.Script):
    def to_html(self):
        def prop_to_html(key):
            yield html.P([html.B(key+": "), html.I(self.yaml_desc.get(key, "[missing]"))])

        def keylist_to_html(key, yaml_desc=self.yaml_desc):
            if not key in yaml_desc: return

            yield html.P(html.B(key+": "))
            lst = [html.Li(e) for e in yaml_desc[key]]

            yield html.Ul(lst)

        def matrix_to_html():
            yield html.P(html.B("matrix:"))

            params = []
            for param, values in self.yaml_desc["matrix"].items():
                items = values.split(", ")
                params.append(html.Li([html.I(param.rpartition("=")[-1]), " → ", " | ".join(items)]))

            if "$webpage" in self.yaml_desc:
                pages = []
                for name, url in self.yaml_desc["$webpage"].items():
                    pages.append(html.A(name, href=url))
                    pages.append(" | ")
                params.append(html.Li([html.I("$webpage"), " → ", html.Span(pages[:-1])]))

            yield html.Ul(params)

        yield from prop_to_html("name")
        yield from prop_to_html("record_time")
        yield from prop_to_html("codec")
        yield from keylist_to_html("before")
        yield from keylist_to_html("after")
        yield from matrix_to_html()

    def do_run_the_matrix(self, exe, webpage_name, res):
        codec_name = self.yaml_desc["codec"]
        record_time = self.yaml_desc["record_time"]
        script_name = self.yaml_desc["name"]
        resolution_str = 'x'.join([res["width"], res["height"]]) if res else "----x----"

        param_lists = []
        for name, values in self.yaml_desc["matrix"].items():
            param_lists.append([(name, value) for value in values.split(", ")])

        if not exe.dry:
            log_filename = f"logs/{script_name}.csv"
            with open(log_filename, "a") as log_f:
                print(f"# {datetime.datetime.now()}", file=log_f)

        expe_skipped = 0
        total_expe = functools.reduce(operator.mul, map(len, param_lists), 1)
        for expe_cnt, param_items in enumerate(itertools.product(*param_lists)):
            param_dict = dict(param_items)
            param_str = ";".join([f"{k}={v}" for k, v in param_items]).replace('gst.prop=', '')

            file_key = " | ".join([webpage_name, f"{record_time}s", codec_name,
                                   param_str, resolution_str])
            exe.log("---")
            exe.log(f"running {expe_cnt}/{total_expe}")
            exe.log("> "+file_key)
            if file_key in matrix_view.Matrix.entry_map:
                # add filename here
                exe.log(f">> already recorded, skipping.")

                expe_skipped += 1
                continue

            exe.reset()

            exe.set_encoding(codec_name, param_dict)
            exe.wait(10)
            exe.clear_graph()
            exe.clear_quality()
            exe.wait(1)
            exe.append_quality(f"script: name: {script_name}")
            exe.append_quality(f"script: encoding: {codec_name} | {', '.join([f'{k}={v}' for k, v in param_dict.items()])}")
            exe.wait(record_time)

            dest = f"logs/{script_name}_{record_time}s_" + \
                datetime.datetime.today().strftime("%Y%m%d-%H%M%S") + ".rec"
            exe.save_graph(dest)

            log_entry = f"{file_key} | {dest}"
            log_filename = f"logs/{script_name}.csv"

            exe.log(f"write log: {log_filename} << {log_entry}")

            if exe.dry: continue

            with open(log_filename, "a") as log_f:
                print(log_entry, file=log_f)

        exe.log(f"Performed {total_expe - expe_skipped} experiments.")
        exe.log(f"Skipped {expe_skipped} experiments already recorded.")

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

            self.log(f"resolution not found, attempt {nb_loops}/{MAX_WAIT_LOOPS}")
            if nb_loops >= MAX_WAIT_LOOPS:
                print("bye")
                return None

    def do_run_webpage(self, exe, name, url, resolution):
        for cmd in self.yaml_desc.get("before", []):
            exe.execute(cmd.replace("$webpage", url))

        self.do_run_the_matrix(exe, name, resolution)

        for cmd in self.yaml_desc.get("after", []): exe.execute(cmd)


    def do_run(self, exe):
        if not matrix_view.Matrix.properties:
            matrix_view.parse_data("logs/matrix.log")

        exe.log("Query frame resolution ...")
        resolution = self.get_resolution(exe)
        if not resolution:
            exe.log("Failed to get the resolution")
            if not exe.dry:
                exe.log("Something's wrong, bye!")
                return

        exe.log("resolution:", resolution)

        for name, url in self.yaml_desc.get("$webpage", {"none": "none"}).items():
            self.do_run_webpage(exe, name, url, resolution)
            exe.log("---")

TYPES = {
    None: SimpleScript,
    "simple": SimpleScript,
    "matrix": MatrixScript,
}
