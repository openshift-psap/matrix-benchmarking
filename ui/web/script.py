import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html
import datetime, time
import os
import threading

import utils.yaml

from . import InitialState, UIState
from . import quality, graph, control

class Script():
    all_scripts = {}
    messages = []
    thr = None

    def __init__(self, yaml_desc):
        self.yaml_desc = yaml_desc
        self.name = yaml_desc["name"]

    def to_id(self):
        return self.yaml_desc["name"].lower().replace(" ", "-")

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
            for codec_name, params_desc in yaml_run.items():
                params = []

                for param_name, param_values in params_desc.items():
                    params += [html.Li([html.I(param_name), ": ", param_values])]

                codecs += [html.Li([codec_name, html.Ul(params)])]

            yield html.Ul(codecs)

        yield from prop_to_html("description")
        yield from keylist_to_html("before")
        yield from run_to_html()
        yield from prop_to_html("wait")
        yield from keylist_to_html("after")

        yield html.Br()

    def log(self, *args):
        Script.messages.append(self.name+": "+" ".join(map(str, args)))

    def run(self, dry):
        def execute(cmd):
            self.log("exec:", cmd)
            if dry: return
            os.system(cmd)

        def set_encoding(codec, params):
            self.log("set_enc:", codec, params)
            if dry: return
            control.set_encoder(codec, params)

        def wait(nb_sec):
            self.log(f"wait: {nb_sec} seconds")
            if dry: return
            time.sleep(nb_sec)

        def clear_quality():
            self.log(f"quality: clear")
            if dry: return
            quality.Quality.clear()

        def append_quality(msg):
            quality_msg = (0, "script", msg)
            self.log(f"quality: append: ", ":".join(quality_msg[1:]))
            if dry: return
            quality.Quality.add_to_quality(*quality_msg)

        def clear_graph():
            self.log(f"graph: clear")
            if dry: return
            graph.DB.clear_graphs()

        def save_graph(fname):
            self.log(f"graph: save into {fname}")
            if dry: return
            graph.DB.save_to_file(fname)

        def do_run():
            Script.messages[:] = []
            self.log("running" + " (dry)" if dry else "!")

            clear_graph()
            clear_quality()
            wait(2)
            append_quality(f"!running: {self.name}")
            for cmd in self.yaml_desc.get("before", []): execute(cmd)

            for codec_name, params_desc in self.yaml_desc["run"].items():
                for param_name, param_values in params_desc.items():
                    for param_value in param_values.split(", "):
                        set_encoding(codec_name, {param_name: param_value})
                        wait(int(self.yaml_desc["wait"]))

            for cmd in self.yaml_desc.get("after", []): execute(cmd)

            append_quality(f"!finished: {self.name}")

            dest = self.to_id() + "_" + datetime.datetime.today().strftime("%Y%m%d-%H%M") + ".db"
            save_graph(dest)

            if not dry: return

            self.log("done!")
            Script.thr = None

        if dry:
            do_run()
        elif Script.thr:
            self.log("Failed, a script thread is already running ...")
        else:
            Script.thr = threading.Thread(target=do_run)
            Script.thr.daemon = True
            Script.thr.start()

def construct_script_tabs():
    Script.all_scripts.clear()

    all_yaml_desc = utils.yaml.load_all("test_cases.yaml")

    for script_yaml_desc in all_yaml_desc:
        if not script_yaml_desc: continue
        if script_yaml_desc.get("disabled", False) is True: continue

        script = Script(script_yaml_desc)
        Script.all_scripts[script.to_id()] = script

        yield dcc.Tab(value=script.to_id(),
                      label=script.name,
                      children=list(script.to_html()))

def construct_script_tab():
    msg_children = [
        dcc.Interval(
            id='script-msg-refresh',
            interval=InitialState.SCRIPT_REFRESH_INTERVAL * 1000
        ),
        html.Div(id="script-msg-box", children=["(no script logs)"],
                 style={"margin-top": "10px", "margin-left": "0px",
                        "padding-left": "10px", "padding-top": "10px",
                        "background-color": "lightblue", "text-align":"left",})
    ]

    children = [
        html.H3(["Test-case scripts ",
                 html.Button('Test', id='script-bt-dry'),
                 html.Button('Run', id='script-bt-run'), "|",
                 html.Button('Refresh', id='script-bt-refresh'),
                 html.Button('Clear', id='script-bt-clear'), "|",
                 html.Button('Reload scripts', id='script-bt-reload'),
        ],
                style={"text-align":"center"}),
        html.P(id="script-msg"),
        html.Div([
            html.Div(msg_children, style={"text-align":"center",}, className="four columns"),
            html.Div(dcc.Tabs(id="script-tabs", children=[]), className="eight columns"),
        ], className="row")
    ]

    return dcc.Tab(label="Scripts", children=children)

def construct_script_tab_callbacks():
    if UIState.VIEWER_MODE: return

    @UIState.app.callback(Output("script-tabs", 'children'),
                          [Input('script-bt-reload', 'n_clicks')])
    def reload_scripts(*args):
        print("Script: reloading")
        return list(construct_script_tabs())

    @UIState.app.callback(Output("script-msg-box", 'children'),
                          [Input('script-msg-refresh', 'n_intervals'),
                           Input('script-bt-dry', 'n_clicks'),
                           Input('script-bt-run', 'n_clicks'),
                           Input('script-bt-refresh', 'n_clicks'),
                           Input('script-bt-clear', 'n_clicks'),
                           Input('script-tabs', "value")])
    def trigger_scripts(kick, dry_n_clicks, run_n_clicks, refresh_n_clicks,
                        clear_n_clicks, tab_name):

        triggered_id = dash.callback_context.triggered[0]["prop_id"]
        if triggered_id == "script-bt-clear.n_clicks" and clear_n_clicks is not None:
            Script.messages[:] = []

        if triggered_id == "script-bt-run.n_clicks" and run_n_clicks is not None or \
           triggered_id == "script-bt-dry.n_clicks" and dry_n_clicks is not None:
            if tab_name in Script.all_scripts:
                script = Script.all_scripts[tab_name]
                Script.messages[:] = []
                dry = triggered_id == "script-bt-dry.n_clicks"
                script.run(dry)
            elif tab_name == "tab-1":
                Script.messages.append(f"please select a script tab first.")
            else:
                Script.messages.append(f"script {tab_name} not found ... (try to reload the scripts)")


        return [html.P(msg, style={"margin-top": "0px", "margin-bottom": "0px"}) \
                for msg in Script.messages]
