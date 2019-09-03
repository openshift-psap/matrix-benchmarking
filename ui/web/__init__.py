import dash
from dash.dependencies import Output, Input
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

app = dash.Dash(__name__)

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


def construct_callback(tab_name, graph_title, graph_spec):
    @app.callback(Output(graph_title_to_id(graph_title), 'figure'),
                  [Input(graph_title_to_id(tab_name)+'-refresh', 'n_intervals')])
    def update_graph_scatter(kick_idx):
        table = get_table_for_spec(graph_spec)
        if not table:
            raise Exception(graph_spec)
            return None
        print(graph_title)
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
            layout.yaxis = dict(range=[min(Y),max(Y)])

            layout.xaxis.title = graph_spec["x"]
            layout.yaxis.title = graph_spec["y"]

        return {'data': [data],'layout' : layout}

def construct_app():
    dataview_cfg = utils.yaml.load_multiple("ui/web/dataview.yaml")

    def graph_list(tab_name, tab_content):
        for graph_title in tab_content:
            print(f" - {graph_title}")
            yield dcc.Graph(id=graph_title_to_id(graph_title))

        yield dcc.Interval(
                id=graph_title_to_id(tab_name)+'-refresh',
                interval=1*1000
            )
    def tab_entries():
        for tab_name, tab_content in dataview_cfg.items():
            print(f"Add {tab_name}")
            yield dcc.Tab(label=tab_name,
                          children=list(graph_list(tab_name, tab_content)))

    app.layout = html.Div([dcc.Tabs(id="tabs", children=list(tab_entries()))])

    for tab_name, tab_content in dataview_cfg.items():
        for graph_title, graph_spec in tab_content.items():
            construct_callback(tab_name, graph_title, graph_spec)

class Server():
    def __init__(self):
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
