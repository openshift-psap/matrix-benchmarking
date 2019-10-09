import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html
import threading
import flask
import sys
import logging

import utils.yaml
from . import matrix_view

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

codec_cfg = utils.yaml.load_multiple("codec_params.yaml")
dataview_cfg = None
main_app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
AgentExperimentClass = None # populated by smart_agent, cannot import it from here
running_as_collector = False

class _UIState():
    def __init__(self, expe=None, viewer_mode=False):
        from . import graph, quality

        self.viewer_mode = viewer_mode
        self.app = main_app
        self.DB = graph.DB()
        self.layout = None

        if expe is None:
            expe = AgentExperimentClass()

        self.DB.expe = expe
        self.DB.expe.new_quality_cb = quality.Quality.add_to_quality

        self.DB.init_quality_from_viewer()

ui_states = {}
class __UIState():
    def __init__(self):
        self.app = main_app

    def __call__(self):
        try:
            key = flask.request.referrer.split("/", maxsplit=3)[-1] # http://host/{key}
        except RuntimeError as e: # Working outside of request context
            if running_as_collector:
                key = "collector"
            else: raise(e)

        return ui_states[key]


UIState = __UIState()

def construct_layout(ui_state):
    from . import live, config, control, script, quality

    def tab_entries():
        yield control.construct_control_center_tab(codec_cfg)

        for graph_tab in dataview_cfg.tabs:
            print(f"Add {graph_tab.tab_name}")
            yield dcc.Tab(label=graph_tab.tab_name,
                          children=list(live.graph_list(graph_tab)))

        if UIState().viewer_mode: return

        yield script.construct_script_tab()
        yield config.construct_config_tab()

    ui_state.app.title = 'Smart Streaming Control Center'
    header = [dcc.Input(id='empty', style={"display": "none"})] + live.construct_header()


    if UIState().viewer_mode:
        header += config.construct_config_stubs()

    return html.Div(header+[dcc.Tabs(id="main-tabs", children=list(tab_entries()))])


def construct_callbacks():
    from . import quality, control, live, config, script

    quality.construct_quality_callbacks()
    control.construct_codec_control_callbacks(codec_cfg)
    live.construct_live_refresh_callbacks(dataview_cfg)
    config.construct_config_tab_callbacks(dataview_cfg)
    script.construct_script_tab_callbacks()

    # Dash doesn't support creating the callbacks AFTER the app is running,
    # can the Matrix callback IDs are dynamic (base on the name of the parameters)
    # So at the moment, only one file can be loaded, here in the startup...
    matrix_view.parse_data("logs/matrix.log")
    matrix_view.build_callbacks(main_app)

def initialize_viewer(url, ui_state):
    from measurement import hot_connect

    filename = "logs/"+url.rpartition("/")[-1]

    hot_connect.load_record_file(ui_state.DB.expe, filename)

    return construct_layout(ui_state)


def construct_dispatcher():
    main_app.config.suppress_callback_exceptions = True

    main_app.layout = html.Div([
        dcc.Location(id='url', refresh=False),
        html.Div(id='page-content')
    ])

    @main_app.callback(Output('page-content', 'children'),
                       [Input('url', 'pathname')])
    def display_page(pathname):
        if pathname is None: return
        url = flask.request.referrer.split("/", maxsplit=3)[-1] # http://host/{key}

        try: return UIState().layout
        except KeyError: pass

        if running_as_collector and pathname.startswith('/collector'):
            return UIState().layout

        elif pathname in ("/viewer", "/viewer/"):
            import glob
            children = [html.P(html.A(filename.rpartition("/")[-1],
                                      href="/viewer/"+(filename.rpartition("/")[-1]),
                                      target="_blank")) \
                        for filename in glob.glob("logs/*.rec")]

            return html.Div(children)

        elif pathname.startswith('/viewer/'):
            try:
                ui_state = _UIState(viewer_mode=True)
                ui_states[url] = ui_state # must remain before init()

                ui_state.layout = initialize_viewer(url, ui_state)

                return ui_state.layout
            except Exception as e:
                del ui_states[url]
                import traceback, sys, os, signal
                print(f"DASH: {e.__class__.__name__}: {e}")
                traceback.print_exception(*sys.exc_info())

                return html.Div(f"Error: {e}")

        elif pathname.startswith('/matrix'):
            return matrix_view.build_layout()
        else:
            if pathname == "/collector":
                msg = "Performance collector not available, running as viewer."
            elif pathname != "/":
                msg = f"Invalid page requested ({pathname})"
            else:
                msg = ""

            index = html.Ul(
                ([html.Li(html.A("Performance Collector", href="/collector"))]
                 if running_as_collector else []) +
                [html.Li(html.A("Viewer index", href="/viewer")),
                 html.Li(html.A("Matrix visualizer", href="/matrix"))])

            return [msg, index]


class Server():
    def __init__(self, expe=None):
        self.thr = threading.Thread(target=self._thr_run_dash)
        self.thr.daemon = True

        self._init_webapp(expe)

    def start(self):
        self.thr.start()

    def terminate(self):
        pass

    def new_table(self, table):
        UIState().DB.new_table(table)

    def new_table_row(self, table, row):
        UIState().DB.new_table_row(table, row)

    def periodic_checkup(self):
        pass

    def _init_webapp(self, expe):
        from . import graph
        global dataview_cfg
        dataview_cfg = graph.DataviewCfg(utils.yaml.load_multiple("ui/web/dataview.yaml"))

        if expe:
            global running_as_collector
            running_as_collector = True
            ui_state = ui_states["collector"] = _UIState(expe, viewer_mode=False)
            ui_state.layout = construct_layout(ui_state)

        construct_dispatcher()
        construct_callbacks()

    def _thr_run_dash(self):
        try:

            main_app.run_server()
        except Exception as e:
            import traceback, sys, os, signal
            print(f"DASH: {e.__class__.__name__}: {e}")
            traceback.print_exception(*sys.exc_info())
            os.kill(os.getpid(), signal.SIGINT)
