import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html
import plotly
import plotly.graph_objs as go
import threading
from collections import deque
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

QUALITY_REFRESH_INTERVAL = 10000 #s
GRAPH_REFRESH_INTERVAL = 10000 #s

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

    add_to_quality("ui", f"New encoder: {encoder_name} || {params_str}")

    return f"{encoder_name} || {params_str}"

def graph_title_to_id(graph_name):
    return graph_name.lower().replace(" ", "-")

def get_table_for_spec(graph_spec):
    if graph_spec in tables_missing:
        return None

    table_name = graph_spec["table"]
    for table in tables_by_name[table_name]:
        for k in "x", "y":
            if graph_spec[k] not in table.fields:
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
    @app.callback(Output("quality-box", 'children'),
                  [Input('quality-refresh', 'n_intervals')],
                  [State("quality-box", 'children')])
    def refresh_quality(timer_kick, quality_children):
        return [html.P(msg, style={"margin-top": "0px", "margin-bottom": "0px"}) \
                for msg in quality]

    @app.callback(Output("quality-input", 'value'),
                  [Input('quality-send', 'n_clicks'),
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
            construct_live_refresh(tab_name, graph_title, graph_spec)

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
                      html.Button('Send!', id='quality-send'),
                      dcc.Interval(
                          id='quality-refresh',
                          interval=QUALITY_REFRESH_INTERVAL * 1000
                      ),
                      html.Div(id="quality-box", children=[
                          html.P("guest:hello", style={"margin-top": "0px", "margin-bottom": "0px"}),
                          html.P("server:hello", style={"margin-top": "0px", "margin-bottom": "0px"}),
                          html.P("client:hello", style={"margin-top": "0px", "margin-bottom": "0px"})
                          ], style={"margin-top": "10px", "margin-left": "0px",
                                    "padding-left": "10px", "padding-top": "10px",
                                    "background-color": "lightblue", "text-align":"left",})

            ], style={"text-align":"center",}, className="four columns"),
            html.Div(codec_tabs, className="eight columns"),
            ], className="row")
    ]

    return dcc.Tab(label="Control center",  children=children)

def construct_live_refresh(tab_name, graph_title, graph_spec):

    @app.callback(Output(graph_title_to_id(graph_title), 'figure'),
                  [Input(graph_title_to_id(tab_name)+'-refresh', 'n_intervals')])
    def update_graph_scatter(timer_kick):
        table = get_table_for_spec(graph_spec)
        if not table:
            raise Exception(graph_spec)
            return None

        content = table_contents[table]

        x_idx = table.fields.index(graph_spec["x"])
        y_idx = table.fields.index(graph_spec["y"])

        X = [row[x_idx] for row in content]
        Y = [row[y_idx] for row in content]

        data = plotly.graph_objs.Scatter(
            x=list(X),
            y=list(Y),
            name='Scatter',
            mode= 'lines+markers'
        )

        layout = go.Layout()
        layout.title=graph_title
        if X and Y:
            layout.xaxis = dict(range=[min(X),max(X)])
            layout.yaxis = dict(range=[min(Y + [0]),max(Y)])

            layout.xaxis.title = graph_spec["x"]
            layout.yaxis.title = graph_spec["y"]

        return {'data': [data],'layout' : layout}

def construct_app():
    dataview_cfg = utils.yaml.load_multiple("ui/web/dataview.yaml")
    codec_cfg = utils.yaml.load_multiple("codec_params.yaml")

    def graph_list(tab_name, tab_content):
        for graph_title in tab_content:
            print(f" - {graph_title}")
            yield dcc.Graph(id=graph_title_to_id(graph_title))

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

    app.title = 'Smart Streaming Control Center'
    app.layout = html.Div([dcc.Tabs(id="main-tabs", children=list(tab_entries()))])

    #---

    construct_quality_callbacks()
    construct_codec_control_callbacks(codec_cfg)
    construct_live_refresh_callbacks(dataview_cfg)


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
