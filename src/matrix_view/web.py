import traceback, sys
import logging

import dash
import dash_html_components as html
import dash_core_components as dcc
from dash.dependencies import Output, Input, State
import flask

import pandas
try: import numpy
except ImportError: pass

import matrix_view
import store

# stylesheets now served via assets/bWLwgP.css and automatically included
main_app = dash.Dash(__name__)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

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

        if pathname.startswith('/viewer/'):
            return  "No viewer yet ..."

        elif pathname.startswith('/matrix'):
            return matrix_view.build_layout(search)

        elif pathname.startswith('/saved'):
            return  "No saved yet ..."

        else:
            msg = f"Invalid page requested ({pathname})" if pathname != "/" else ""

            index = html.Ul(
                [html.Li(html.A("Saved records index)", href="/viewer"))] +
                [html.Li(html.A("Saved graphs index", href="/saved"))] +
                ([html.Li(html.A("Matrix visualizer", href="/matrix"))]))

            return [msg, index]


def run(mode_store, mode):
    matrix_view.build_callbacks(main_app)
    display_page = construct_dispatcher()

    generate = store.experiment_filter.pop("__generate__", False)
    if generate:
        print(f"Generating http://127.0.0.1:8050/matrix?{generate.replace(' ', '%20')} ...")

        page = matrix_view.build_layout(generate, serializing=True)


        for param in page.children[0].children:
            if not isinstance(param, dcc.Dropdown): continue
            print(param.id)
            if param.id != "list-params-stats": continue
            stats = param.value
            break
        else:
            stats = []
        if not stats:
            print("WARNING: could not find any stats enabled ...")
        if isinstance(stats, str):
            stats = [stats]

        idx = 0
        for graph in page.children[1].children[::2]:
            if not isinstance(graph, dcc.Graph):
                #print("Not a graph...", graph)
                continue
            figure = graph.figure
            dest = f"{idx}_{stats[idx].replace(' ', '_')}"
            print(f"Saving {dest} ...")
            figure.write_html(f"../{dest}.html")
            figure.write_image(f"../{dest}.png")
            idx += 1

        sys.exit(0)

    try: main_app.run_server()
    except OSError as e:
        if e.errno == 98:
            print(f"FATAL: Dash server port already in use. Is this perf_collector already running?")
        else:
            print(f"DASH: {e.__class__.__name__}: {e}")
            traceback.print_exception(*sys.exc_info())
    except Exception as e:
        print(f"DASH: {e.__class__.__name__}: {e}")
        traceback.print_exception(*sys.exc_info())
