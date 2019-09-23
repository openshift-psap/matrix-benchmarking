import dash
from dash.dependencies import Output, Input, State, ClientsideFunction
import dash_core_components as dcc
import dash_html_components as html

import plotly
import plotly.graph_objs as go

from . import InitialState, UIState
from . import graph

def graph_list(graph_tab):
    for graph_spec in graph_tab.graphs:
        print(f" - {graph_spec.graph_name}")
        yield html.H3(graph_spec.graph_name, id=graph_spec.to_id()+'-title',
                      style={'text-align': "center", "font-size": "17px", "fill":"rgb(68, 68, 68)",
                             'margin-bottom': '0rem'})
        yield dcc.Graph(id=graph_spec.to_id())

        yield html.Div(id=graph_spec.to_id()+":clientside-output")

    if UIState.VIEWER_MODE: return

    yield dcc.Interval(
        id=graph_tab.to_id()+'-refresh',
        interval=InitialState.GRAPH_REFRESH_INTERVAL * 1000
    )

def construct_header():
    headers = []
    if UIState.VIEWER_MODE: return headers

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

        # vh = view height, 100 == all the visible screen
        VH_MAX = 75

        if n_clicks is None:
            if graph_spec.yaml_desc.get("_collapsed"):
                height = "5vh"
            else:
                nb_visible = sum([1 for _graph_spec in graph_tab.graphs
                                  if not _graph_spec.yaml_desc.get("_collapsed")])

                height = f"{(1/nb_visible*VH_MAX):.0f}vh"

        elif "height" in style and style["height"] == f"{VH_MAX}vh":
            height = f"{(1/len(graph_tab.graphs)*VH_MAX):.0f}vh"

            title_style["color"] = ""
        else:
            height = f"{VH_MAX}vh"
            title_style["color"] = "green"

        style["height"] = height

        return style, title_style

    scatter_input = Input('url', 'pathname') if UIState.VIEWER_MODE else \
                    Input(graph_tab.to_id()+'-refresh', 'n_intervals')
    @UIState.app.callback(Output(graph_spec.to_id(), 'figure'),
                          [scatter_input])
    def update_graph_scatter(*args):
        if not UIState.DB.table_contents:
            return {}

        tbl = graph.DbTableForSpec.get_table_for_spec(graph_spec)
        if not tbl:
            raise NameError(graph_spec.yaml_desc)

        content = UIState.DB.table_contents[tbl.table]
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
        if UIState.DB.quality_by_table[tbl.table]:
            quality_x = []
            quality_y = []
            quality_msg = []
            for row, msg in UIState.DB.quality_by_table[tbl.table]:
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
