import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html

from . import InitialState, UIState
from . import graph, quality

def construct_config_stubs():
    yield dcc.Input(type='number', value=0, id='graph-view-length')

def construct_config_tab():
    if UIState.VIEWER_MODE:
        return html.Div([tag for tag in construct_config_stubs()])

    children = [
        "Graph refresh period: ",
        dcc.Slider(min=0, max=100, step=2, value=InitialState.GRAPH_REFRESH_INTERVAL-1,
                   marks={0:"1s", 100:"100s"}, id="cfg:graph-refresh"),
        html.Br(),
        "Script refresh period: ",
        dcc.Slider(min=0, max=100, step=1, value=InitialState.SCRIPT_REFRESH_INTERVAL,
                   marks={0:"0s", 100:"100s"}, id="cfg:script-refresh"),
        html.Br(),
        "Number of seconds to show on the live graph: ",
        dcc.Input(type='number', value=InitialState.LIVE_GRAPH_NB_SECONDS_TO_KEEP,
                  id='graph-view-length'),
    ]

    return dcc.Tab(label="Config", children=children)

def construct_config_tab_callbacks(dataview_cfg):
    if UIState.VIEWER_MODE: return

    @UIState.app.callback(Output("script-msg-refresh", 'interval'),
                          [Input('cfg:script-refresh', 'value')])
    def update_script_refresh_timer(value):
        if value == 0: value = 9999
        print(f"Refresh scripts every {value}s")
        return value * 1000

    @UIState.app.callback(Output("quality-refresh", 'interval'),
                          [Input('cfg:quality', 'value')])
    def update_quality_refresh_timer(value):
        if value == 0: value = 9999
        return value * 1000

    @UIState.app.callback(Output("cfg:quality:value", 'children'),
                          [Input('cfg:quality', 'value')])
    def update_quality_refresh_label(value):
        return f" every {value} seconds"

    # ---

    marker_cnt = 0
    @UIState.app.callback(Output('graph-header-msg', 'children'),
                          [Input('graph-bt-save', 'n_clicks'),
                           Input('graph-bt-marker', 'n_clicks'),
                           Input('graph-bt-clear', 'n_clicks'),])
    def action_graph_button(save, marker, clear):
        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        if triggered_id == "graph-bt-marker.n_clicks":
            if marker is None: return
            nonlocal marker_cnt
            quality.Quality.add_to_quality(0, "ui", f"!Marker {marker_cnt}")
            marker_cnt += 1
            return

        if triggered_id == "graph-bt-save.n_clicks":
            if save is None: return
            DEST = "save.rec"
            print("Saving into", DEST, "...")
            graph.DB.save_to_file(DEST)
            print("Saving: done")

            return ""

        if triggered_id == "graph-bt-clear.n_clicks":
            if clear is None: return
            graph.DB.clear_graphs()
            print("Graphs cleared!")
            return

        print("click not handled... ", triggered_id, save, marker, clear)
        return ""

    @UIState.app.callback(Output("cfg:graph:value", 'children'),
                          [Input('cfg:graph-refresh', 'value'), Input('graph-bt-stop', 'n_clicks')])
    def update_graph_refresh_label(value, bt_n_click):
        return f" every {value+1} seconds "

    @UIState.app.callback(Output("graph-bt-stop", 'children'),
                          [Input('graph-bt-stop', 'n_clicks')])
    def update_graph_refresh_label(bt_n_click):
        if bt_n_click is not None and bt_n_click % 2:
            return "Restart"
        else:
            return "Pause"

    outputs = [Output(graph_tab.to_id()+'-refresh', 'interval')
               for graph_tab in dataview_cfg.tabs]

    @UIState.app.callback(outputs,
                          [Input('cfg:graph-refresh', 'value'),
                           Input('graph-bt-stop', 'n_clicks')])
    def update_graph_refresh_timer(value, stop_n_click):
        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        if triggered_id == "graph-bt-stop.n_clicks":
            if stop_n_click is not None and stop_n_click % 2:
                value = 9999

        # from the slider, min = 1
        value += 1

        return [value * 1000 for _ in outputs]
