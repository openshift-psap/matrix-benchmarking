import dash
from dash.dependencies import Output, Input, State, ClientsideFunction
import dash_core_components as dcc
import dash_html_components as html

import plotly
import plotly.graph_objs as go

import datetime

from . import InitialState, UIState
from . import graph

# vh = view height, 100 == all the visible screen
GRAPH_MAX_VH_HEIGHT = 75
GRAPH_MIN_VH_HEIGHT = 75/3

def graph_list(graph_tab):
    for graph_spec in graph_tab.graphs:
        print(f" - {graph_spec.graph_name}")
        yield html.H3(graph_spec.graph_name, id=graph_spec.to_id()+'-title',
                      style={'text-align': "center", "font-size": "17px", "fill":"rgb(68, 68, 68)",
                             'margin-bottom': '0rem'})

        height = max((1/len(graph_tab.graphs)*GRAPH_MAX_VH_HEIGHT), GRAPH_MIN_VH_HEIGHT)
        yield dcc.Graph(id=graph_spec.to_id(),
                        style={"height":f"{height:.0f}vh"})

        yield html.Div(id=graph_spec.to_id()+":clientside-output")


    refresh_interval = 9999999 if UIState().viewer_mode else InitialState.GRAPH_REFRESH_INTERVAL * 1000

    yield dcc.Interval(
        id=graph_tab.to_id()+'-refresh',
        interval=refresh_interval)

def construct_header():
    headers = []
    if UIState().viewer_mode: return headers

    return headers + ["Refreshing graph ", html.Span(id="cfg:graph:value"),
            html.Button('', id='graph-bt-stop'),
            html.Button('Save', id='graph-bt-save'),
            html.Button('Clear', id='graph-bt-clear'),
            html.Button('Insert marker', id='graph-bt-marker'),
            html.Span(id='graph-header-msg'),
            html.Br(), html.Br()
    ]

def construct_live_refresh_callbacks(dataview_cfg):
    for graph_tab in dataview_cfg.tabs:
        for graph_spec in graph_tab.graphs:
            construct_live_refresh_cb(graph_tab, graph_spec)

def construct_live_refresh_cb(graph_tab, graph_spec):
    UIState.app.clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="resize_graph"),
        Output(graph_spec.to_id()+":clientside-output", "children"),
        [Input(graph_spec.to_id(), "style")],
    )

    @UIState.app.callback([Output(graph_spec.to_id(), 'style'),
                            Output(graph_spec.to_id()+'-title', 'style')],
                           [Input(graph_spec.to_id()+'-title', 'n_clicks')],
                           [State(graph_spec.to_id(), 'style'),
                            State(graph_spec.to_id()+'-title', 'style')])
    def update_graph_style(n_clicks, style, title_style):
        if style is None: style = {}

        if n_clicks is None or "height" in style and style["height"] == f"{GRAPH_MAX_VH_HEIGHT}vh":
            nb_visible = sum([1 for _graph_spec in graph_tab.graphs
                              if not _graph_spec.yaml_desc.get("_collapsed")])

            _height = max((1/len(graph_tab.graphs)*GRAPH_MAX_VH_HEIGHT), GRAPH_MIN_VH_HEIGHT)
            height = f"{_height:.0f}vh"

            title_style["color"] = ""
        else:
            height = f"{GRAPH_MAX_VH_HEIGHT}vh"
            title_style["color"] = "green"

        style["height"] = height

        return style, title_style

    scatter_input = Input(graph_tab.to_id()+'-refresh', 'n_intervals')
    @UIState.app.callback(Output(graph_spec.to_id(), 'figure'),
                          [scatter_input,
                          Input("graph-view-length", "value")])
    def update_graph_scatter(*args):
        if not UIState().DB.table_contents:
            return {}

        tbl = graph.DbTableForSpec.get_table_for_spec(graph_spec)
        if not tbl:
            title = f"No table for {graph_spec.yaml_desc}"
            return {'data': [],'layout' : dict(title=title)}

        content = UIState().DB.table_contents[tbl.table]
        X = tbl.get_x()

        nb_seconds_to_keep = args[-1]
        records_to_drop = 0
        if nb_seconds_to_keep != 0 and X and isinstance(X[0], datetime.datetime):
            for records_to_drop, v in enumerate(X):
                if (X[-1] - v).total_seconds() <= nb_seconds_to_keep: break

        X_cut = X[records_to_drop:]
        plots = []
        y_max = 0
        for y_field, Y in tbl.get_all_y(X):
            y_max = max([y for y in Y if y is not None] + [y_max])

            plots.append(
                plotly.graph_objs.Scatter(
                    x=X_cut, y=Y[records_to_drop:],
                    name=y_field.label,
                    mode=graph_spec.mode))

        layout = go.Layout()
        layout.hovermode = "closest"
        layout.showlegend = True

        try:
            layout.xaxis = dict(range=[min(X_cut), max(X_cut)])
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
        if UIState().DB.quality_by_table[tbl.table]:
            quality_x = []
            quality_y = []
            quality_msg = []
            for row, msg in UIState().DB.quality_by_table[tbl.table]:
                quality_x.append(row[tbl.idx(graph_spec.x)])
                quality_y.append(y_max / 2)
                quality_msg.append(msg)

            plots.append(
                go.Scatter(
                    x=graph_spec.x.modify(quality_x, None),
                    y=quality_y,
                    name="Quality",
                    hovertext=quality_msg,
                    mode="markers",
                    marker=dict(color="green"),
                )
            )

        layout.shapes = shapes

        return {'data': plots,'layout' : layout}
