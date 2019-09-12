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
    QUALITY_REFRESH_INTERVAL = 1 #s
    SCRIPT_REFRESH_INTERVAL = 1 #s

class UIState():
    VIEWER_MODE = False
    app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    DB = None


def module_late_init(expe):
    from . import live, control, graph, quality, config, script

    UIState.DB = graph.DB

    UIState.DB.expe = expe
    UIState.DB.expe.new_quality_cb = quality.Quality.add_to_quality
    UIState.DB.init_quality_from_viewer()

def construct_app():
    dataview_cfg = graph.DataviewCfg(utils.yaml.load_multiple("ui/web/dataview.yaml"))
    codec_cfg = utils.yaml.load_multiple("codec_params.yaml")

    def tab_entries():
        yield control.construct_control_center_tab(codec_cfg)

        for graph_tab in dataview_cfg.tabs:
            print(f"Add {graph_tab.tab_name}")
            yield dcc.Tab(label=graph_tab.tab_name,
                          children=list(live.graph_list(graph_tab)))

        if not UIState.VIEWER_MODE:
            yield script.construct_script_tab()

        yield config.construct_config_tab()

    UIState.app.title = 'Smart Streaming Control Center'
    header = [dcc.Location(id='url', refresh=False)] + live.construct_header()

    UIState.app.layout = html.Div(header+[dcc.Tabs(id="main-tabs", children=list(tab_entries()))])

    #---

    quality.construct_quality_callbacks()
    control.construct_codec_control_callbacks(codec_cfg)
    live.construct_live_refresh_callbacks(dataview_cfg)
    config.construct_config_tab_callbacks(dataview_cfg)
    script.construct_script_tab_callbacks()

class Server():
    def __init__(self, expe):
        module_late_init(expe)

        self.thr = threading.Thread(target=self._thr_run_dash)
        self.thr.daemon = True

    def start(self):
        import measurement.perf_viewer
        UIState.VIEWER_MODE = measurement.perf_viewer.viewer_mode

        construct_app()
        self.thr.start()

    def terminate(self):
        pass

    def new_table(self, table):
        # table_name might not be unique ...
        UIState.DB.table_definitions[table] = table
        UIState.DB.table_contents[table] = []
        UIState.DB.tables_by_name[table.table_name].append(table)

    def new_table_row(self, table, row):
        UIState.DB.table_contents[table].append(row)

    def periodic_checkup(self):
        pass

    def _thr_run_dash(self):
        try:
            UIState.app.run_server()
        except Exception as e:
            import traceback, sys, os, signal
            print(f"DASH: {e.__class__.__name__}: {e}")
            traceback.print_exception(*sys.exc_info())
            os.kill(os.getpid(), signal.SIGINT)
