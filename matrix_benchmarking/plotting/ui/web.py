import traceback, sys, os
import logging

import dash
from dash import html
from dash import dcc
from dash.dependencies import Output, Input, State
import flask

import pandas
try: import numpy
except ImportError: pass

import matrix_benchmarking.plotting.ui as ui
import matrix_benchmarking.store as store
import matrix_benchmarking.cli_args as cli_args
import matrix_benchmarking.plotting.table_stats as table_stats
import matrix_benchmarking.plotting.ui.report as report

IMAGE_WIDTH = int(os.environ.get("MATBENCH_PLOTTING_IMAGE_WIDTH", 1200))
IMAGE_HEIGHT = int(os.environ.get("MATBENCH_PLOTTING_IMAGE_HEIGHT", 650))

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
            return ui.build_layout(search)

        elif pathname.startswith('/saved'):
            return  "No saved yet ..."

        else:
            msg = f"Invalid page requested ({pathname})" if pathname != "/" else ""

            index = html.Ul(
                [html.Li(html.A("Saved records index)", href="/viewer"))] +
                [html.Li(html.A("Saved graphs index", href="/saved"))] +
                ([html.Li(html.A("Matrix visualizer", href="/matrix"))]))

            return [msg, index]


def run():
    ui.build_callbacks(main_app)
    display_page = construct_dispatcher()

    generate = cli_args.kwargs["generate"]

    if generate:
        logging.info(f"Generating http://127.0.0.1:8050/matrix?{generate.replace(' ', '%20')} ...")

        page = ui.build_layout(generate, serializing=True)

        idx = -1
        content = page.children[1].children
        report_index_f = open("reports_index.html", "w")
        print("<ul>", file=report_index_f)

        for graph, text in zip(content[0::2], content[1::2]):
            if not isinstance(graph, dcc.Graph):
                continue
            idx += 1

            stats = table_stats.TableStats.stats_by_id[graph.id]

            if getattr(stats, "is_report", False):
                report.generate(idx, graph.id, text, report_index_f)
                continue

            figure = graph.figure
            if not figure:
                continue

            dest = f"{idx:02d}_{graph.id.replace(' ', '_').replace('/', '_')}"

            logging.info(f"Saving {dest} ...")
            figure.write_html(f"fig_{dest}.html")
            figure.write_image(f"fig_{dest}.png", width=IMAGE_WIDTH, height=IMAGE_HEIGHT)

            if text and text.children:
                for child in text.children:
                    if not child: continue
                    logging.info(child)
        print("</ul>", file=report_index_f)
        report_index_f.close()

        sys.exit(0)

    try: main_app.run_server()
    except OSError as e:
        if e.errno == 98:
            logging.error(f"Dash server port already in use ...")
        else:
            logging.error(f"DASH: {e.__class__.__name__}: {e}")
            traceback.print_exception(*sys.exc_info())
    except Exception as e:
        logging.error(f"DASH: {e.__class__.__name__}: {e}")
        traceback.print_exception(*sys.exc_info())
