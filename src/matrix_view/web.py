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

def run(store, mode):
    matrix_view.build_callbacks(main_app)
    construct_dispatcher()

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
