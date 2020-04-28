import sys, os, threading
import logging

import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html
import flask

import pandas

try: import numpy
except ImportError: pass

import utils.yaml
from . import matrix_view

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

LISTEN_ON = None

class InitialState():
    GRAPH_REFRESH_INTERVAL = 1 #s
    QUALITY_REFRESH_INTERVAL = 0 #s
    SCRIPT_REFRESH_INTERVAL = 0 #s
    LIVE_GRAPH_NB_SECONDS_TO_KEEP = 2*60 #s

driver_settings_cfg = None
dataview_cfg = None

AgentExperimentClass = None # populated by local_agent, cannot import it from here
running_as_collector = False
machines = None

# stylesheets now served via assets/bWLwgP.css and automatically included
main_app = dash.Dash(__name__)

class _UIState():
    def __init__(self, url, expe=None, viewer_mode=False):
        from . import graph, quality

        self.viewer_mode = viewer_mode
        self.app = main_app
        self.DB = graph.DB()
        self.layout = None

        if expe is None:
            expe = AgentExperimentClass()

        self.DB.expe = expe
        self.DB.expe.new_quality_cbs.append(quality.Quality.add_to_quality)

        self.DB.init_quality_from_viewer()

        self.url = url

ui_states = {}
class __UIState():
    def __init__(self):
        self.app = main_app

    def __call__(self):
        if running_as_collector:
            key = "collector"
            return ui_states[key]

        try:
            url = threading.current_thread().url
        except AttributeError as e: # 'Thread' object has no attribute 'url'
            url = flask.request.url

        if url.endswith(".rec"):
            # url: http://host/{key}
            key = url.split("/", maxsplit=3)[-1]
        elif url.endswith("/_dash-update-component"): # common case
            url = flask.request.referrer
            if url is None:
                msg = "Warning: cannot get the proper URL ..."
                print(msg)
                raise RuntimeError(msg)
            # url: http://host/{key}
            key = url.split("/", maxsplit=3)[-1]
        else:
            # url: http://host/{key}/<whatever>
            key = url.split("/", maxsplit=3)[-1].partition("/")[0]

        return ui_states[key]


UIState = __UIState()

def construct_layout(ui_state):
    from . import live, config, control, script, quality

    def tab_entries():
        yield control.construct_control_center_tab(driver_settings_cfg)

        for graph_tab in dataview_cfg.tabs:
            print(f"Add {graph_tab.tab_name}")
            yield dcc.Tab(label=graph_tab.tab_name,
                          children=list(live.graph_list(graph_tab)))

        if UIState().viewer_mode: return

        yield config.construct_config_tab()

    ui_state.app.title = 'Streaming Stats Control Center'
    header = [dcc.Input(id='empty', style={"display": "none"})] \
        + live.construct_header()


    if UIState().viewer_mode:
        header += config.construct_config_stubs()

    return html.Div(header+[dcc.Tabs(id="main-tabs", children=list(tab_entries()))])


def construct_collector_callbacks(mode, running_as_collector):
    from . import quality, control, live, config

    quality.construct_quality_callbacks()
    control.construct_driver_control_callbacks(driver_settings_cfg)
    live.construct_live_refresh_callbacks(dataview_cfg)

    if not running_as_collector: return

    config.construct_config_tab_callbacks(dataview_cfg)

def construct_matrix_callbacks(mode):
    # Dash doesn't support creating the callbacks AFTER the app is running,
    # can the Matrix callback IDs are dynamic (base on the name of the parameters)
    # So at the moment, only one file can be loaded, here in the startup...
    import glob
    from . import script

    expe_arg = sys.argv[-1]
    what = expe_arg if not "/" in expe_arg \
        and os.path.exists(f"{script.RESULTS_PATH}/{expe_arg}/matrix.csv") \
        else "*"

    matrix_view.configure(mode)

    for matrix_result in glob.glob(f"{script.RESULTS_PATH}/{what}/matrix.csv"):
        matrix_view.parse_data(matrix_result)

    matrix_view.build_callbacks(main_app)

def initialize_viewer(url, ui_state):
    from measurement import hot_connect

    _viewer, _result, path = url.split("/", maxsplit=2)

    if not (_viewer == "viewer" and _result == "results"):
        raise RuntimeError(f"Invalid url prefix ... {_viewer}/{_result} ...")

    filename = os.path.abspath(os.sep.join([script.RESULTS_PATH, path]))
    if not filename.startswith(script.RESULTS_PATH):
        raise RuntimeError(f"Filename abs path ({filename}) doesn't start "
                           f"with the right prefix {script.RESULTS_PATH} ...")

    hot_connect.load_record_file(ui_state.DB.expe, filename)

    return construct_layout(ui_state)


def construct_dispatcher():
    main_app.config.suppress_callback_exceptions = True

    main_app.layout = html.Div([
        dcc.Location(id='url', refresh=False),
        html.Div(id='page-content')
    ])

    @main_app.callback(Output('page-content', 'children'),
                       [Input('url', 'pathname'), Input('url', 'search')])
    def display_page(pathname, search):
        if pathname is None: return
        url = flask.request.referrer.split("/", maxsplit=3)[-1] # http://host/{key}

        try: return UIState().layout
        except KeyError: pass

        if running_as_collector and pathname.startswith('/collector'):
            return UIState().layout

        elif pathname in ("/viewer", "/viewer/"):
            from pathlib import Path

            path = script.RESULTS_PATH
            children = [html.P(html.A(str(filename)[len(path)+1:],
                                      href="/viewer/results/"+(str(filename)[len(path)+1:]),
                                      target="_blank")) \
                        for filename in Path(path).rglob('*.rec') ]
            return html.Div([html.H3("Saved records")] + children)

        elif pathname.startswith('/viewer/') and pathname.endswith(".rec"):
            def load_viewer():
                try:
                    ui_state = _UIState(url, viewer_mode=True)
                    ui_states[url] = ui_state # must remain before init()
                    ui_state.layout = initialize_viewer(url, ui_state)
                except Exception as e:
                    del ui_states[url]
                    import traceback, sys, os, signal
                    print(f"load_viewer: {e.__class__.__name__}: {e}")
                    traceback.print_exception(*sys.exc_info())

            t = threading.Thread(target=load_viewer)
            t.daemon = True # we cannot join it ...
            t.url = flask.request.url_root + url
            t.start() # run load_viewer() in a thread to avoid timeout
            return  "Loading ..." # might not be shown because of very short timeout  -,-

        elif pathname.startswith('/viewer/') and ".rec/" in pathname:
            # pathname  = /viewer/[<path>/]<file>/<other args>

            _key, _, args = pathname[1:].partition(".rec/")
            key = _key + ".rec"

            if args.startswith("pipeline/"):
                try: db = ui_states[key].DB
                except KeyError: return html.Div(f"Error: key '{key}' not found, is the viewer loaded?")
                idx, _, ext = args.partition("/")[-1].partition(".")

                return quality.get_pipeline(db, int(idx), ext)
            else:
                return html.Div(f"Error: invalid url {pathname}")

        elif pathname.startswith('/matrix'):
            if running_as_collector:
                return ["Matrix visualiser not available, running as ", html.A("collector", href="/collector"), "."]

            return matrix_view.build_layout(search)
        elif pathname.startswith('/saved'):
            path = f"{script.RESULTS_PATH}/../saved"

            if pathname.endswith(".dill"):
                filepath = pathname[len("/saved/"):]
                if '..' in filepath: return "invalid path ..."
                import dill
                try:
                    with open(path+"/"+filepath, 'rb') as dill_f:
                        return dill.load(diff_f)
                except Exception as e:
                    return f"Failed to open '{pathname}' ... ({e.__class__.__name__})"
            else:
                from pathlib import Path
                children = [html.P(html.A(str(filename)[len(path)+1:],
                                          href="/saved/"+(str(filename)[len(path)+1:]),
                                          target="_blank")) \
                            for filename in Path(path).rglob('*.dill')]

                return html.Div([html.H3("Saved graphs")] + children)
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
                [html.Li(html.A("Saved records (viewer index)", href="/viewer"))] +
                [html.Li(html.A("Saved graphs (loaded index)", href="/saved"))] +
                ([html.Li(html.A("Matrix visualizer", href="/matrix"))]
                 if not running_as_collector else []))

            return [msg, index]

class Server():
    def __init__(self, expe=None, headless=False, cfg={}):
        thr_fct = self._thr_run_headless_and_quit if headless \
            else self._thr_run_dash

        self.thr = threading.Thread(target=thr_fct)
        self.thr.daemon = True

        self.cfg = cfg
        self._configure()

        self.expe = expe

        if headless:
            assert expe is not None, "No expe received in headless collector mode ..."

        if expe:
            self._init_collector(expe, headless)

        if not headless:
            self._init_webapp(expe)

    def _configure(self):
        if not self.cfg: return

        from . import graph
        global dataview_cfg
        dataview_cfg = graph.DataviewCfg(utils.yaml.load_multiple(f"cfg/{self.cfg['mode']}/dataview.yaml"))

        global driver_settings_cfg
        driver_settings_cfg  = utils.yaml.load_multiple(f"cfg/{self.cfg['mode']}/driver_settings.yaml")

        global machines
        machines = self.cfg['machines']

        # ---
        from . import control
        control.configure(self.cfg['mode'], self.cfg['plugin'], self.cfg['machines'])

        global LISTEN_ON
        LISTEN_ON = self.cfg["setup"].get('listen_on', None)

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

    def _init_collector(self, expe, headless=False):
        global running_as_collector
        running_as_collector = True
        ui_state = ui_states["collector"] = _UIState("collector", expe, viewer_mode=False)

        if not headless:
            ui_state.layout = construct_layout(ui_state)
            UIState()

    def _init_webapp(self, expe):
        construct_dispatcher()
        construct_collector_callbacks(self.cfg["mode"], running_as_collector)

        if running_as_collector: return

        construct_matrix_callbacks(self.cfg["mode"])

    def _thr_run_dash(self):
        try:
            main_app.run_server(host=LISTEN_ON)
        except Exception as e:
            import traceback, sys, os, signal
            print(f"DASH: {e.__class__.__name__}: {e}")
            traceback.print_exception(*sys.exc_info())
            os.kill(os.getpid(), signal.SIGINT)

    def _thr_run_headless_and_quit(self):
        try:
            self._thr_run_headless()
        except Exception as e:
            import traceback, sys
            print(f"HEADLESS: {e.__class__.__name__}: {e}")
            traceback.print_exception(*sys.exc_info())
            raise e
        finally:
            import signal, os
            os.kill(os.getpid(), signal.SIGTERM)

    def _thr_run_headless(self):
        from . import script

        class message_to_print():
            def append(self, msg): print(msg)
            def insert(self, pos, msg): pass
            def clear(self): pass

        matrix_view.configure(self.cfg["mode"])

        script.Script.messages = message_to_print()

        script.Script.load(self.cfg["mode"], self.expe)
        try:
            script_name = self.cfg['headless']['script']
            script_to_run = script.Script.all_scripts[script_name]
        except KeyError:
            print(f"ERROR: script not found '{script_name}'...")
            return
        import sys
        dry = "run" not in sys.argv
        thr = script_to_run.run(dry=dry)
        if thr:
            thr.join()
