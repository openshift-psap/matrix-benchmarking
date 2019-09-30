import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html
import threading

import utils.yaml

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

external_stylesheets = [
    'https://codepen.io/chriddyp/pen/bWLwgP.css' # see https://codepen.io/chriddyp/pen/bWLwgP for style/columnts
]

class InitialState():
    GRAPH_REFRESH_INTERVAL = 1 #s
    QUALITY_REFRESH_INTERVAL = 0 #s
    SCRIPT_REFRESH_INTERVAL = 0 #s
    LIVE_GRAPH_NB_SECONDS_TO_KEEP = 2*60 #s

class _UIState():
    VIEWER_MODE = False
    app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    DB = None

ui_state = _UIState()
def UIState():
    return ui_state

def module_late_init(expe):
    from . import live, control, graph, quality, config, script
    ui_state = UIState()

    ui_state.DB = graph.DB

    ui_state.DB.expe = expe
    ui_state.DB.expe.new_quality_cb = quality.Quality.add_to_quality
    ui_state.DB.init_quality_from_viewer()

def construct_app():
    dataview_cfg = graph.DataviewCfg(utils.yaml.load_multiple("ui/web/dataview.yaml"))
    codec_cfg = utils.yaml.load_multiple("codec_params.yaml")
    ui_state = UIState()

    def tab_entries():
        yield control.construct_control_center_tab(codec_cfg)

        for graph_tab in dataview_cfg.tabs:
            print(f"Add {graph_tab.tab_name}")
            yield dcc.Tab(label=graph_tab.tab_name,
                          children=list(live.graph_list(graph_tab)))

        yield config.construct_config_tab()

    ui_state.app.title = 'Smart Streaming Control Center'
    header = [dcc.Input(id='empty', style={"display": "none"})] + live.construct_header()

    if ui_state.VIEWER_MODE:
        header += config.construct_config_stubs()

    layout = html.Div(header+[dcc.Tabs(id="main-tabs", children=list(tab_entries()))])

    #---

    quality.construct_quality_callbacks()
    control.construct_codec_control_callbacks(codec_cfg)
    live.construct_live_refresh_callbacks(dataview_cfg)
    config.construct_config_tab_callbacks(dataview_cfg)
    script.construct_script_tab_callbacks()

    return layout

def construct_dispatcher():
    ui_state = UIState()
    ui_state.app.config.suppress_callback_exceptions = True
    viewer_layout = construct_app()

    ui_state.app.layout = html.Div([
        dcc.Location(id='url', refresh=False),
        html.Div(id='page-content')
    ])
    @ui_state.app.callback(Output('page-content', 'children'),
                           [Input('url', 'pathname')])
    def display_page(pathname):
        from flask import request
        print(request.referrer, pathname)
        if pathname is None:
            return "RIEN"
        if ui_state.VIEWER_MODE and pathname.startswith('/viewer'):
            return viewer_layout
        elif not ui_state.VIEWER_MODE and pathname.startswith('/collector'):
            return viewer_layout
        else:
            return request.referrer

class Server():
    def __init__(self, expe):
        module_late_init(expe)

        self.thr = threading.Thread(target=self._thr_run_dash)
        self.thr.daemon = True

    def start(self):
        import measurement.perf_viewer
        UIState().VIEWER_MODE = measurement.perf_viewer.viewer_mode

        construct_dispatcher()
        self.thr.start()

    def terminate(self):
        pass

    def new_table(self, table):
        ui_state = UIState()

        # table_name might not be unique ...
        ui_state.DB.table_definitions[table] = table
        ui_state.DB.table_contents[table] = []
        ui_state.DB.tables_by_name[table.table_name].append(table)

    def new_table_row(self, table, row):
        UIState().DB.table_contents[table].append(row)

    def periodic_checkup(self):
        pass

    def _thr_run_dash(self):
        try:
            UIState().app.run_server()
        except Exception as e:
            import traceback, sys, os, signal
            print(f"DASH: {e.__class__.__name__}: {e}")
            traceback.print_exception(*sys.exc_info())
            os.kill(os.getpid(), signal.SIGINT)
