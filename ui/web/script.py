import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html
import os, time, datetime
import threading
import types

import utils.yaml

from . import InitialState, UIState
from . import quality, graph, control

class PythonExec:
    stress_test_state = types.SimpleNamespace()

    @staticmethod
    def stress_test(exe, resources):
        from . import machines
        from . import stress_test
        stress_test.stress_test(PythonExec.stress_test_state, exe, resources, machines)

class Exec():
    def __init__(self, script, dry):
        self.dry = dry
        self.script = script
        self.total_wait_time = 0

    def log(self, *args, ahead=False):
        msg = " ".join(map(str, args))
        if self.dry:
            if ahead:
                Script.messages.insert(0, msg)
            Script.messages.append(msg)

        else:
            print(datetime.datetime.now().strftime("%H:%M:%S"), msg)
            Script.messages.insert(0, msg)

    def execute(self, cmd):
        if cmd.startswith("/py/"):
            fct_name, _, args = cmd[5:].partition(" ")
            fct = getattr(PythonExec, fct_name)
            self.log(f"python-exec: {fct.__qualname__}({args})")
            fct(self, args)
        else:
            self.log("system-exec:", cmd)
            if self.dry: return
            os.system(cmd)

    def set_encoding(self, codec, params, force=False):
        self.log("set_enc:", codec, ', '.join([f"{k}={v}" for k, v in params.items()]))
        if self.dry and not force: return
        control.set_encoder(codec, params)

    def request(self, msg, client=False, agent=False, force=False):
        if not (client or agent):
            print(f"ERROR: send '{msg}' to nobody ...")
            return

        whom = (['agent'] if agent else []) + (['client'] if client else [])
        self.log(f"request: send '{msg}' to {', '.join(whom)}")

        if self.dry and not force: return

        rq = dict()
        if client: rq['client-request'] = msg
        if agent: rq['streaming-agent-request'] = msg

        control.send_qmp(rq)

    def wait(self, nb_sec):
        self.log(f"wait {nb_sec} seconds")
        self.total_wait_time += nb_sec
        if self.dry: return
        time.sleep(nb_sec)

    def clear_quality(self):
        self.log(f"clear quality")
        if self.dry: return
        quality.Quality.clear()

    def append_quality(self, msg):
        quality_msg = (0, "script", msg)
        self.log(f"append to quality:", ": ".join(quality_msg[1:]))
        if self.dry: return
        quality.Quality.add_to_quality(*quality_msg)

    def clear_record(self):
        self.log(f"clear graphs")
        if self.dry: return
        UIState().DB.clear_graphs()

    def save_record(self, fname):
        if os.path.exists(fname):
            self.log(f"WARNING: record destination '{fname}' already exists ...")
            fname = fname + "_" + datetime.datetime.now().strftime("%y%m%d_%H%M%S")

        self.log(f"save record into {fname}")
        if self.dry:
            # make sure that we can create this file
            open(fname, "w")
            os.unlink(fname)
        else:
            UIState().DB.save_to_file(fname)

    def reset_encoder(self):
        self.log(f"reset encoder parameters")
        if self.dry: return
        control.set_encoder("reset", {})

class Script():
    all_scripts = {}
    messages = []
    thr = None

    @staticmethod
    def load(fname="test_cases.yaml"):
        from . import script_types

        Script.all_scripts.clear()

        all_yaml_desc = utils.yaml.load_all(fname)

        for script_yaml_desc in all_yaml_desc:
            if not script_yaml_desc: continue
            if script_yaml_desc.get("disabled", False) is True: continue
            _type = script_yaml_desc.get("_type")
            try:
                script_type = script_types.TYPES[_type]
            except KeyError:
                print(f"WARNING: script: invalid script type ({_type})")
                continue

            script = script_type(script_yaml_desc)
            Script.all_scripts[script.to_id()] = script

    def __init__(self, yaml_desc):
        self.yaml_desc = yaml_desc
        self.name = yaml_desc["name"]

    def to_id(self):
        return self.yaml_desc["name"].lower().replace(" ", "-")

    def to_html(self):
        yield "nothing"

    def run(self, dry):
        exe = Exec(self, dry)
        def connected(): return UIState().DB.expe.agents_connected()
        if dry:
            exe.log(f"Running {self.name} (dry)")
            self.do_run(exe)
            exe.log(f"Estimated time: {exe.total_wait_time/60:.0f}min{exe.total_wait_time%60}s", ahead=True)
        elif Script.thr:
            exe.log("Failed, a script thread is already running ...")
        else:
            def run_thr(exe):
                Script.messages.clear()
                exe.log(f"Running {self.name}!")
                TOTAL_AGENTS_CNT = 3
                while len(connected()) != TOTAL_AGENTS_CNT:
                    print(f"Agents connected: {','.join(connected())}")
                    print(f"Waiting to have {TOTAL_AGENTS_CNT} ...")
                    time.sleep(1)

                exe.log(f"Agents connected: {', '.join(connected())}")
                self.do_run(exe)
                exe.log(f"Agents connected: {', '.join(connected())}")
                Script.thr = None

            Script.thr = threading.Thread(target=run_thr, args=(exe,))
            Script.thr.daemon = True
            Script.thr.start()

            return Script.thr


def construct_script_inner_tabs():
    for script in Script.all_scripts.values():
        yield dcc.Tab(value=script.to_id(), label=script.name,
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
    @UIState.app.callback(Output("script-tabs", 'children'),
                          [Input('script-bt-reload', 'n_clicks')])
    def reload_scripts(*args):
        print("Script: reloading")
        Script.load()

        return list(construct_script_inner_tabs())

    @UIState.app.callback(Output("script-msg-box", 'children'),
                          [Input('script-msg-refresh', 'n_intervals'),
                           Input('script-bt-dry', 'n_clicks'),
                           Input('script-bt-run', 'n_clicks'),
                           Input('script-bt-refresh', 'n_clicks'),
                           Input('script-bt-clear', 'n_clicks'),
                           Input('script-tabs', "value")])
    def trigger_scripts(kick, dry_n_clicks, run_n_clicks, refresh_n_clicks,
                        clear_n_clicks, tab_name):

        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

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
