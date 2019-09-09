import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html
import plotly
import plotly.graph_objs as go
import threading
import datetime
from collections import defaultdict
import json
import statistics

import utils.yaml

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

class DB():
    expe = None

    tables_by_name = defaultdict(list)
    table_definitions = {}
    table_contents = {}
    quality_by_table = defaultdict(list)

    @staticmethod
    def save_to_file(filename):
        output = open(filename, "w")
        print(json.dumps(Quality.quality), file=output)

        for table in DB.expe.tables:
            print(table.header(), file=output)
            print(json.dumps(DB.table_contents[table]), file=output)
            print(json.dumps(DB.quality_by_table[table]), file=output)

    @staticmethod
    def init_quality_from_viewer():
        import measurement.perf_viewer
        measurement.perf_viewer.Perf_Viewer.quality_for_ui = DB.quality_by_table

class Quality():
    quality = []

    @staticmethod
    def add_to_quality(ts, src, msg):
        Quality.quality.insert(0, (ts, src, msg))

        if msg.startswith("!"):
            Quality.add_quality_to_plots(msg)

    @staticmethod
    def add_quality_to_plots(msg):
        for table, content in DB.table_contents.items():
            if not content: continue

            DB.quality_by_table[table].append((content[-1], msg))


class DbTableForSpec():
    table_for_spec = {}

    @staticmethod
    def get_table_for_spec(graph_spec):
        try: return DbTableForSpec.table_for_spec[str(graph_spec.yaml_desc)]
        except KeyError: pass

        for table in DB.tables_by_name[graph_spec.table]:
            for ax in graph_spec.all_axis:
                if ax.field_name not in table.fields:
                    break
            else: # didn't break, all the fields are present
                break
        else: # didn't break, table not found
            print(f"WARNING: No table found for {graph_spec.yaml_desc}")
            table = None
            table_for_spec = None

        if table:
            table_for_spec = DbTableForSpec(table, graph_spec)

        DbTableForSpec.table_for_spec[str(graph_spec.yaml_desc)] = table_for_spec

        return table_for_spec

    def __init__(self, table, graph_spec):
        self.table = table
        self.graph_spec = graph_spec

        self.content = DB.table_contents[table]

    def idx(self, field):
        return self.table.fields.index(field.field_name)

    def get(self, field):
        idx = self.idx(field)

        values = [(row[idx]) for row in self.content]

        return list(field.modify(values))

    def get_first_raw_x(self):
        return self.content[0][self.idx(self.graph_spec.x)]

    def get_x(self):
        return self.get(self.graph_spec.x)

    def get_all_y(self):
        for y_field in self.graph_spec.all_y_axis:
            yield y_field, self.get(y_field)

class FieldSpec():
    def __init__(self, yaml_desc):
        field_modif, has_label, label = yaml_desc.partition(">")

        self.field_name, _, modif = field_modif.partition("|")
        self.field_name = self.field_name.strip()

        self.label = label if has_label else self.field_name

        try:
            self.modify = getattr(GraphFormat, modif.strip())
        except AttributeError:
            self.modify = lambda x:x

class GraphSpec():
    def __init__(self, graph_name, yaml_desc):
        self.graph_name = graph_name
        self.yaml_desc = yaml_desc
        self.table = yaml_desc["table"]

        self.x = FieldSpec(yaml_desc["x"])

        self.all_y_axis = []
        for ax in "y", "y2", "y3", "y4":
            try:
                self.all_y_axis.append(FieldSpec(yaml_desc[ax]))
            except KeyError: pass
        self.all_axis = [self.x] + self.all_y_axis

        try:
            self.y_max = self.yaml_desc["y_max"]
        except KeyError: pass

        try:
            self.y_title = self.yaml_desc["y_title"]
        except KeyError: pass

    def get_spec(self, name):
        return self.yaml_desc[name]

    def to_id(self):
        return self.graph_name.lower().replace(" ", "-")


class GraphTabContent():
    def __init__(self, tab_name, yaml_desc):
        self.tab_name = tab_name
        self.yaml_desc = yaml_desc

        self.graphs = [GraphSpec(graph_name, graph_spec)
                       for graph_name, graph_spec in self.yaml_desc.items()]

    def to_id(self):
        return self.tab_name.lower().replace(" ", "-")

class DataviewCfg():
    def __init__(self, yaml_desc):
        self.yaml_desc = yaml_desc

        self.tabs = [GraphTabContent(tab_name, graph_tab_content)
                     for tab_name, graph_tab_content in self.yaml_desc.items()]


external_stylesheets = [
    'https://codepen.io/chriddyp/pen/bWLwgP.css' # see https://codepen.io/chriddyp/pen/bWLwgP for style/columnts
]

VIEWER_MODE = False

QUALITY_REFRESH_INTERVAL = 5 #s
GRAPH_REFRESH_INTERVAL = 1 #s

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)


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

    Quality.add_to_quality(None, "ui", f"!Set encoder: {encoder_name} || {params_str}")

    return f"{encoder_name} || {params_str}"

def construct_codec_control_callback(codec_name):
    if VIEWER_MODE: return

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
                  [Input('quality-refresh', 'n_intervals')])
    def refresh_quality(*args):
        return [html.P(f"{src}: {msg}", style={"margin-top": "0px", "margin-bottom": "0px"}) \
                for (ts, src, msg) in Quality.quality]

    if VIEWER_MODE: return

    @app.callback(Output("quality-refresh", 'n_intervals'),
                  [Input('quality-bt-clear', 'n_clicks'), Input('quality-bt-refresh', 'n_clicks')])
    def clear_quality(clear_n_clicks, refresh_n_clicks):

        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        if triggered_id == "quality-bt-clear.n_clicks":
            if clear_n_clicks is None: return

            Quality.quality[:] = []
        else:
            if refresh_n_clicks is None: return
            # forced refresh, nothing to do

        return 0

    @app.callback(Output("quality-input", 'value'),
                  [Input('quality-bt-send', 'n_clicks'),
                   Input('quality-input', 'n_submit'),],
                  [State(component_id='quality-input', component_property='value')])
    def quality_send(n_click, n_submit, quality_value):
        if not quality_value:
            return ""

        if not DB.expe:
            return "<error: expe not set>"

        DB.expe.send_quality(quality_value)

        return "" # empty the input text

def construct_live_refresh_callbacks(dataview_cfg):
    for graph_tab in dataview_cfg.tabs:
        for graph_spec in graph_tab.graphs:
            construct_live_refresh_cb(graph_tab, graph_spec)

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

    quality_children = [
        html.H3("Quality Messages", style={"text-align":"center"}),
        dcc.Interval(
            id='quality-refresh',
            interval=QUALITY_REFRESH_INTERVAL * 1000
        )
    ]

    quality_area = html.Div(id="quality-box", children=[],
                            style={"margin-top": "10px", "margin-left": "0px",
                                   "padding-left": "10px", "padding-top": "10px",
                                   "background-color": "lightblue", "text-align":"left",})

    if VIEWER_MODE:
        tab_children = quality_children + [quality_area]
    else:
        quality_children += [
            dcc.Input(placeholder='Enter a quality message...', type='text', value='', id="quality-input"),
            html.Button('Send!', id='quality-bt-send'),
            html.Button('Clear', id='quality-bt-clear'),
            html.Button('Refresh', id='quality-bt-refresh'),
            html.Br(),
            "Refreshing quality ", html.Span(id="cfg:quality:value"),
            dcc.Slider(min=0, max=30, step=2, value=QUALITY_REFRESH_INTERVAL,
                       marks={0:"0s", 30:"30s"},
                       id="cfg:quality"), html.Br(),
            quality_area]

        tab_children = [
            html.Div([
                html.Div(quality_children, style={"text-align":"center",}, className="four columns"),
                html.Div(codec_tabs, className="eight columns"),
            ], className="row")
        ]

    return dcc.Tab(label="Control center", children=tab_children)

def construct_live_refresh_cb(graph_tab, graph_spec):
    @app.callback(Output(graph_spec.to_id(), 'figure'),
                  [Input(graph_tab.to_id()+'-refresh', 'n_intervals')])
    def update_graph_scatter(timer_kick):
        tbl = DbTableForSpec.get_table_for_spec(graph_spec)
        if not tbl:
            raise NameError(graph_spec.yaml_desc)

        content = DB.table_contents[tbl.table]
        X = tbl.get_x()

        plots = []
        y_max = 0
        for y_field, Y in tbl.get_all_y():
            y_max = max(Y + [y_max])

            plots.append(
                plotly.graph_objs.Scatter(
                    x=X, y=Y,
                    name=y_field.label,
                    mode= 'lines'))

        layout = go.Layout()
        layout.hovermode = "closest"
        layout.showlegend = True
        layout.title = graph_spec.graph_name

        try:
            layout.xaxis = dict(range=[min(X), max(X)])
        except ValueError: pass # X is empty
        layout.xaxis.title = graph_spec.x.label

        try:
            y_max = graph_spec.y_max
        except AttributeError: pass # use actual y_max
        layout.yaxis = dict(range=[0, y_max])
        try:
            layout.yaxis.title = graph_spec.y_title
        except AttributeError: pass

        shapes = []
        if DB.quality_by_table[tbl.table]:
            quality_x = []
            quality_y = []
            quality_msg = []
            for row, msg in DB.quality_by_table[tbl.table]:
                quality_x.append(row[tbl.idx(graph_spec.x)])
                quality_y.append(y_max / 2)
                quality_msg.append(msg)

            plots.append(
                go.Scatter(
                    x=graph_spec.x.modify(quality_x),
                    y=quality_y,
                    name="Quality",
                    hovertext=quality_msg,
                    mode="markers",
                    marker=dict(color="green"),
                )
            )

        layout.shapes = shapes

        return {'data': plots,'layout' : layout}

def construct_config_tab():
    children = []

    if not VIEWER_MODE:
        children += [
            "Graph refresh period: ",
            dcc.Slider(min=0, max=100, step=2, value=GRAPH_REFRESH_INTERVAL-1,
                       marks={0:"1s", 100:"100s"}, id="cfg:graph"),
            html.Br()
        ]
    else:
        children += ["Nothing yet in viewer mode"]

    return dcc.Tab(label="Config", children=children)

def construct_config_tab_callbacks(dataview_cfg):
    if VIEWER_MODE: return

    @app.callback(Output("quality-refresh", 'interval'),
                  [Input('cfg:quality', 'value')])
    def update_quality_refresh_timer(value):
        if VIEWER_MODE: return 9999999

        if value == 0: value = 9999
        return value * 1000

    @app.callback(Output("cfg:quality:value", 'children'),
                  [Input('cfg:quality', 'value')])
    def update_quality_refresh_label(value):
        return f" every {value} seconds"

    # ---

    marker_cnt = 0
    @app.callback(Output('graph-header-msg', 'children'),
                  [Input('graph-bt-save', 'n_clicks'),
                   Input('graph-bt-marker', 'n_clicks'),
                   Input('graph-bt-clear', 'n_clicks'),])
    def action_graph_button(save, marker, clear):
        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        if triggered_id == "graph-bt-marker.n_clicks":
            if marker is None: return
            nonlocal marker_cnt
            Quality.add_to_quality(0, "ui", f"Marker {marker_cnt}")
            marker_cnt += 1
            return

        if triggered_id == "graph-bt-save.n_clicks":
            if save is None: return
            DEST = "save.db"
            print("Saving into", DEST, "...")
            DB.save_to_file(DEST)
            print("Saving: done")

            return ""

        if triggered_id == "graph-bt-clear.n_clicks":
            if clear is None: return
            for content in DB.table_contents.values():
                content[:] = []
            DB.quality_by_table .clear()
            print("Cleaned!")
            return

        print("click not handled... ", triggered_id, save, marker, clear)
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

    outputs = [Output(graph_tab.to_id()+'-refresh', 'interval')
               for graph_tab in dataview_cfg.tabs]

    @app.callback(outputs,
                  [Input('cfg:graph', 'value'),
                   Input('graph-bt-stop', 'n_clicks')])
    def update_graph_refresh_timer(value, bt_n_click):
        if VIEWER_MODE: return 99999

        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        if triggered_id == "graph-bt-stop.n_clicks":
            if bt_n_click is not None and bt_n_click % 2:
                value = 9999

        # from the slider, min = 1
        value += 1

        return [value * 1000 for _ in outputs]



def construct_app():
    dataview_cfg = DataviewCfg(utils.yaml.load_multiple("ui/web/dataview.yaml"))
    codec_cfg = utils.yaml.load_multiple("codec_params.yaml")

    def graph_list(graph_tab):
        height = f"{(1/len(graph_tab.graphs)*80):0f}vh"
        for graph_spec in graph_tab.graphs:
            print(f" - {graph_spec.graph_name}")
            yield dcc.Graph(id=graph_spec.to_id(), style={'height': height})


        yield dcc.Interval(
            id=graph_tab.to_id()+'-refresh',
            interval=GRAPH_REFRESH_INTERVAL * 1000
        )

    def tab_entries():
        yield construct_control_center_tab(codec_cfg)

        for graph_tab in dataview_cfg.tabs:
            print(f"Add {graph_tab.tab_name}")
            yield dcc.Tab(label=graph_tab.tab_name,
                          children=list(graph_list(graph_tab)))

        yield construct_config_tab()

    app.title = 'Smart Streaming Control Center'
    header = []
    if not VIEWER_MODE:
        header += [ "Refreshing graph ", html.Span(id="cfg:graph:value"),
                   html.Button('', id=f'graph-bt-stop'),
                   html.Button('Save', id=f'graph-bt-save'),
                   html.Button('Clear', id=f'graph-bt-clear'),
                   html.Button('Insert marker', id=f'graph-bt-marker'),
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
    def as_B_to_GB(lst, first=None):
        return [v/1000/1000 for v in lst]

    @staticmethod
    def avg_20(lst, first=None):
        from collections import deque
        cache = deque(maxlen=20)
        cache += lst[:cache.maxlen]

        avg = []
        for e in lst:
            cache.append(e)
            avg.append(statistics.mean(cache))

        return avg

    @staticmethod
    def as_it_is(lst, first=None):
        print(lst)
        return lst

    @staticmethod
    def as_timestamp(lst, first=None):
        return [datetime.datetime.fromtimestamp(t) for t in lst]

    @staticmethod
    def as_mm_time(lst, first=None):
        if first is None and lst: first = lst[0]

        return [(v - first)/1000 for v in lst]

    @staticmethod
    def as_guest_time(lst, first=None):
        if first is None and lst: first = lst[0]

        return [(v - first) for v in lst]

class Server():
    def __init__(self, expe):
        DB.expe = expe
        DB.expe.new_quality_cb = Quality.add_to_quality
        DB.init_quality_from_viewer()

        self.thr = threading.Thread(target=self._thr_run_dash)
        self.thr.daemon = True

    def start(self):
        import measurement.perf_viewer
        global VIEWER_MODE
        VIEWER_MODE = measurement.perf_viewer.viewer_mode

        construct_app()
        self.thr.start()

    def terminate(self):
        pass

    def new_table(self, table):
        # table_name might not be unique ...
        DB.table_definitions[table] = table
        DB.table_contents[table] = []
        DB.tables_by_name[table.table_name].append(table)

    def new_table_row(self, table, row):
        DB.table_contents[table].append(row)

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
