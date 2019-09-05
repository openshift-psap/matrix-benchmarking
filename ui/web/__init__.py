import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html
import plotly
import plotly.graph_objs as go
import threading
import datetime
from collections import defaultdict
import utils.yaml

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

tables_by_name = defaultdict(list)
table_definitions = {}
table_contents = {}

tables_missing = []

external_stylesheets = [
    'https://codepen.io/chriddyp/pen/bWLwgP.css' # see https://codepen.io/chriddyp/pen/bWLwgP for style/columnts
]

QUALITY_REFRESH_INTERVAL = 5 #s
GRAPH_REFRESH_INTERVAL = 1 #s

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
expe = None

quality = []
def add_to_quality(ts, src, msg):
    quality.insert(0, f"{src}: {msg}")


VIRSH_VM_NAME = "fedora30"

def set_encoder(encoder_name, parameters):
    import os
    import json

    params_str = ";".join(f"{name+'=' if not name.startswith('_') else ''}{value}" for name, value in parameters.items() if value) + ";"
    json_msg = json.dumps(dict(execute="set-spice",
                               arguments={"guest-encoder": encoder_name,
                                          "guest-encoder-params": params_str}))

    cmd = f"virsh qemu-monitor-command {VIRSH_VM_NAME} '{json_msg}'"
    os.system(cmd)

    add_to_quality(None, "ui", f"New encoder: {encoder_name} || {params_str}")

    return f"{encoder_name} || {params_str}"

def graph_title_to_id(graph_name):
    return graph_name.lower().replace(" ", "-")

def get_table_for_spec(graph_spec):
    if graph_spec in tables_missing:
        return None

    table_name = graph_spec["table"]
    for table in tables_by_name[table_name]:
        for k in "x", "y":
            field = graph_spec[k].partition("|")[0].partition(">")[0].strip()
            if field not in table.fields:
                break
        else: # didn't break
            return table

    print(f"WARNING: No table found for {graph_spec}")
    tables_missing.append(graph_spec)
    return None

def construct_codec_control_callback(codec_name):
    cb_states = [State(tag_id, tag_cb_field) \
                 for tag_id, tag_cb_field, _ in control_center_boxes[codec_name]]

    param_names = [tag_id.rpartition(":")[-1] for tag_id, tag_cb_field, _ in control_center_boxes[codec_name]]
    @app.callback(Output(f"{codec_name}-msg", 'children'),
                  [Input(f'{codec_name}-go-button', "n_clicks")],
                  cb_states)
    def activate_codec(*args):
        n_clicks, *states = args
        if n_clicks is None: return # button creation

        params = dict(zip(param_names, states))

        return set_encoder(codec_name, params)

    for tag_id, tag_cb_field, need_value_cb in control_center_boxes[codec_name]:
        if not need_value_cb: continue

        @app.callback(Output(f"{tag_id}:value", 'children'),
                      [Input(tag_id, tag_cb_field)])
        def value_callback(value):
            return f": {value}"

def construct_codec_control_callbacks(codec_cfg):
    for codec_name, options in codec_cfg.items():
        if codec_name == "all": continue
        if options and "_disabled" in options: continue

        construct_codec_control_callback(codec_name)

def construct_quality_callbacks():
    @app.callback(Output("quality-refresh", 'n_intervals'),
                  [Input('quality-bt-clear', 'n_clicks'), Input('quality-bt-refresh', 'n_clicks')])
    def clear_quality(clear_n_clicks, refresh_n_clicks):

        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        if triggered_id == "quality-bt-clear.n_clicks":
            if clear_n_clicks is None: return

            quality[:] = []
        else:
            if refresh_n_clicks is None: return
            # forced refresh, nothing to do

        return 0


    @app.callback(Output("quality-box", 'children'),
                  [Input('quality-refresh', 'n_intervals'),
                   #Input('quality-bt-refresh', 'n_clicks'),
                  ])
    def refresh_quality(*args):
        return [html.P(msg, style={"margin-top": "0px", "margin-bottom": "0px"}) \
                for msg in quality]

    @app.callback(Output("quality-input", 'value'),
                  [Input('quality-bt-send', 'n_clicks'),
                   Input('quality-input', 'n_submit'),],
                  [State(component_id='quality-input', component_property='value')])
    def quality_send(n_click, n_submit, quality_value):
        if not quality_value:
            return ""

        if not expe:
            return "<error: expe not set>"

        expe.send_quality(quality_value)

        return "" # empty the input text

def construct_live_refresh_callbacks(dataview_cfg):
    for tab_name, tab_content in dataview_cfg.items():
        for graph_title, graph_spec in tab_content.items():
            construct_live_refresh_cb(tab_name, graph_title, graph_spec)

control_center_boxes = defaultdict(list)

def construct_control_center_tab(codec_cfg):

    def get_option_box(codec_name, option):
        if option is None:
            option = "custom"

        tag = None
        tag_cb_field = "value"
        need_value_cb = False

        if isinstance(option, dict):
            key, value = list(option.items())[0]
            opt_name = key.capitalize()

            if isinstance(value, str):
                if value.startswith("int["): # int[start:end:step]=default
                    range_str, _, default = value[4:].partition("]=")
                    _min, _max, _step = map(int, range_str.split(":"))
                    marks = {_min:_min, _max:_max}
                    tag = dcc.Slider(min=_min, max=_max, step=_step, value=int(default), marks=marks)
                    need_value_cb = True
                elif value.startswith("int"):

                    default = int(value.partition("=")[-1]) if value.startswith("int=") else ""

                    tag = dcc.Input(placeholder=f'Enter a numeric value for "{option}"',
                                    type='number', value=default, style={"width": "100%"})
                    need_value_cb = True

        if tag is None:
            if not isinstance(option, str):
                raise Exception(f"Option not handled ... {option}")

            opt_name = option.capitalize()
            tag = dcc.Input(placeholder=f'Enter a value for "{option}"', type='text',
                            style={"width": "100%"})

        tag_id = f"{codec_name}-opt:{opt_name.lower()}"
        tag.id = tag_id

        control_center_boxes[codec_name].append((tag_id, tag_cb_field, need_value_cb))

        return [html.P(children=[opt_name, html.Span(id=tag_id+":value")],
                       style={"text-align": "center"}),
                html.P([tag])]

    def get_codec_params(codec_name):
        all_options = codec_cfg.get("all", []) + \
            (codec_cfg[codec_name] if codec_cfg[codec_name] is not None else [])

        for option in all_options:
            yield from get_option_box(codec_name, option)

        yield from get_option_box(codec_name, None)

        yield html.P(id=f"{codec_name}-msg", style={"text-align":"center"})

    def get_codec_tabs():
        for codec_name, options in codec_cfg.items():
            if codec_name == "all": continue
            if options and "_disabled" in options: continue

            print(f"Create {codec_name} tab ...")
            children = []
            children += get_codec_params(codec_name)
            children += [html.Div([html.Button('Go!', id=f'{codec_name}-go-button')],
                                  style={"text-align": "center"})]

            yield dcc.Tab(label=codec_name, children=children)

    codec_tabs = [
        html.H3("Video Encoding", style={"text-align":"center"}),
        dcc.Tabs(id="video-enc-tabs", children=list(get_codec_tabs())),
    ]

    children = [
        html.Div([
            html.Div([html.H3("Quality Messages", style={"text-align":"center"}),
                      dcc.Input(placeholder='Enter a quality message...', type='text', value='', id="quality-input"),
                      html.Button('Send!', id='quality-bt-send'),
                      html.Button('Clear', id='quality-bt-clear'),
                      html.Button('Refresh', id='quality-bt-refresh'),
                      html.Br(),
                      "Refreshing quality ", html.Span(id="cfg:quality:value"),
                      dcc.Slider(min=0, max=30, step=2, value=QUALITY_REFRESH_INTERVAL,
                                 marks={0:"0s", 30:"30s"},
                                 id="cfg:quality"), html.Br(),
                      dcc.Interval(
                          id='quality-refresh',
                          interval=QUALITY_REFRESH_INTERVAL * 1000
                      ),
                      html.Div(id="quality-box", children=[],
                          style={"margin-top": "10px", "margin-left": "0px",
                                    "padding-left": "10px", "padding-top": "10px",
                                    "background-color": "lightblue", "text-align":"left",})

            ], style={"text-align":"center",}, className="four columns"),
            html.Div(codec_tabs, className="eight columns"),
            ], className="row")
    ]

    return dcc.Tab(label="Control center",  children=children)

def construct_live_refresh_cb(tab_name, graph_title, graph_spec):

    @app.callback(Output(graph_title_to_id(graph_title), 'figure'),
                  [Input(graph_title_to_id(tab_name)+'-refresh', 'n_intervals')])
    def update_graph_scatter(timer_kick):
        table = get_table_for_spec(graph_spec)
        if not table:
            raise Exception(graph_spec)
            return None

        content = table_contents[table]

        x_field, _, x_modifier = graph_spec["x"].partition("|")

        x_idx = table.fields.index(x_field.strip())
        X = [(row[x_idx]) for row in content]

        if x_modifier:
            try:
                modify = getattr(GraphFormat, x_modifier.strip())
                X = modify(X)
            except AttributeError: pass

        X = list(X)

        plots = []
        y_max = 0
        for y_name in "y", "y2", "y3", "y4":
            try:
                y_spec = graph_spec[y_name]
            except KeyError: continue

            y_def, has_label, y_label = y_spec.partition(">")

            y_field, _, y_modifier = y_def.partition("|")

            y_name = y_label if has_label else y_field

            y_idx = table.fields.index(y_field.strip())
            Y = [row[y_idx] for row in content]
            if not Y: continue

            if y_modifier:
                try:
                    modify = getattr(GraphFormat, y_modifier.strip())
                    Y = modify(Y)
                except AttributeError: pass

            y_max = max(Y + [y_max])

            plots.append(
                plotly.graph_objs.Scatter(
                    x=X, y=list(Y),
                    name=y_name,
                    mode= 'lines'))

        layout = go.Layout()
        layout.showlegend = True
        layout.title = graph_title

        if X:
            layout.xaxis = dict(range=[min(X), max(X)])
            layout.xaxis.title = graph_spec["x"]

        if Y:
            try:
                y_max = graph_spec["y_max"]
            except KeyError: pass # use actual y_max

            layout.yaxis = dict(range=[0, y_max])
            try:
                layout.yaxis.title = graph_spec["y_title"]
            except KeyError: pass


        return {'data': plots,'layout' : layout}

def construct_config_tab():
    children = [
        "Graph refresh period: ",
        dcc.Slider(min=0, max=100, step=2, value=GRAPH_REFRESH_INTERVAL-1,
                   marks={0:"1s", 100:"100s"}, id="cfg:graph"),
        html.Br()
    ]

    return dcc.Tab(label="Config", children=children)

def construct_config_tab_callbacks(dataview_cfg):
    @app.callback(Output("quality-refresh", 'interval'),
                  [Input('cfg:quality', 'value')])
    def update_quality_refresh_timer(value):
        if value == 0: value = 9999
        return value * 1000

    @app.callback(Output("cfg:quality:value", 'children'),
                  [Input('cfg:quality', 'value')])
    def update_quality_refresh_label(value):
        return f" every {value} seconds"

    # ---

    @app.callback(Output('graph-header-msg', 'children'),
                  [Input('graph-bt-save', 'n_clicks'),
                   Input('graph-bt-clear', 'n_clicks'),])
    def action_graph_button(save, clear):
        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        if triggered_id == "graph-bt-save.n_clicks":
            if save is None: return

            return "save"
        if triggered_id == "graph-bt-clear.n_clicks":
            if clear is None: return
            for content in table_contents.values():
                content[:] = []
            print("Cleaned!")


        return ""

    @app.callback(Output("cfg:graph:value", 'children'),
                  [Input('cfg:graph', 'value'), Input('graph-bt-stop', 'n_clicks')])
    def update_graph_refresh_label(value, bt_n_click):
        return f" every {value+1} seconds "

    @app.callback(Output("graph-bt-stop", 'children'),
                  [Input('graph-bt-stop', 'n_clicks')])
    def update_graph_refresh_label(bt_n_click):
        if bt_n_click is not None and bt_n_click % 2:
            return "Restart"
        else:
            return "Pause"

    outputs = [Output(graph_title_to_id(tab_name)+'-refresh', 'interval')
               for tab_name in dataview_cfg]

    @app.callback(outputs,
                  [Input('cfg:graph', 'value'),
                   Input('graph-bt-stop', 'n_clicks')])
    def update_graph_refresh_timer(value, bt_n_click):
        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        if triggered_id == "graph-bt-stop.n_clicks":
            if bt_n_click is not None and bt_n_click % 2:
                value = 9999

        # from the slider, min = 1
        value += 1

        return [value * 1000 for _ in outputs]



def construct_app():
    dataview_cfg = utils.yaml.load_multiple("ui/web/dataview.yaml")
    codec_cfg = utils.yaml.load_multiple("codec_params.yaml")

    def graph_list(tab_name, tab_content):
        height = f"{(1/len(tab_content)*80):0f}vh"
        for graph_title in tab_content:
            print(f" - {graph_title}")
            yield dcc.Graph(id=graph_title_to_id(graph_title), style={'height': height})

        yield dcc.Interval(
                id=graph_title_to_id(tab_name)+'-refresh',
                interval=GRAPH_REFRESH_INTERVAL * 1000
            )
    def tab_entries():
        yield construct_control_center_tab(codec_cfg)
        for tab_name, tab_content in dataview_cfg.items():
            print(f"Add {tab_name}")
            yield dcc.Tab(label=tab_name,
                          children=list(graph_list(tab_name, tab_content)))

        yield construct_config_tab()

    app.title = 'Smart Streaming Control Center'
    header = [ "Refreshing graph ", html.Span(id="cfg:graph:value"),
               html.Button('', id=f'graph-bt-stop'),
               html.Button('Save', id=f'graph-bt-save'),
               html.Button('Clear', id=f'graph-bt-clear'),
               html.Span(id='graph-header-msg'),
               html.Br(), html.Br()
    ]
    app.layout = html.Div(header+[dcc.Tabs(id="main-tabs", children=list(tab_entries()))])

    #---

    construct_quality_callbacks()
    construct_codec_control_callbacks(codec_cfg)
    construct_live_refresh_callbacks(dataview_cfg)
    construct_config_tab_callbacks(dataview_cfg)

class GraphFormat():
    @staticmethod
    def as_B_to_GB(lst):
        return [v/1000/1000 for v in lst]

    @staticmethod
    def as_it_is(lst):
        print(lst)
        return lst

    @staticmethod
    def as_timestamp(lst):
        return [datetime.datetime.fromtimestamp(t) for t in lst]

    @staticmethod
    def as_mm_time(lst):
        return [(v - lst[0])/1000 for v in lst]

    @staticmethod
    def as_guest_time(lst):
        return [(v - lst[0]) for v in lst]

class Server():
    def __init__(self, _expe):
        global expe; expe = _expe

        expe.new_quality_cb = add_to_quality

        self.thr = threading.Thread(target=self._thr_run_dash)
        self.thr.daemon = True

        construct_app()

        self.thr.start()

    def terminate(self):
        pass

    def new_table(self, table):
        # table_name might not be unique ...
        table_definitions[table] = table
        table_contents[table] = []
        tables_by_name[table.table_name].append(table)

    def new_table_row(self, table, row):
        table_contents[table].append(row)

    def periodic_checkup(self):
        pass

    def _thr_run_dash(self):
        try:
            app.run_server()
        except Exception as e:
            import traceback, sys, os, signal
            print(f"DASH: {e.__class__.__name__}: {e}")
            traceback.print_exception(*sys.exc_info())
            os.kill(os.getpid(), signal.SIGINT)
