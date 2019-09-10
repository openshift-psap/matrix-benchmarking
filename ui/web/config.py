import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html

from . import InitialState, UIState

def construct_config_tab():
    children = []

    if not UIState.VIEWER_MODE:
        children += [
            "Graph refresh period: ",
            dcc.Slider(min=0, max=100, step=2, value=InitialState.GRAPH_REFRESH_INTERVAL-1,
                       marks={0:"1s", 100:"100s"}, id="cfg:graph"),
            html.Br()
        ]
    else:
        children += ["Nothing yet in viewer mode"]

    return dcc.Tab(label="Config", children=children)

def construct_config_tab_callbacks(dataview_cfg):
    if UIState.VIEWER_MODE: return

    @UIState.app.callback(Output("quality-refresh", 'interval'),
                          [Input('cfg:quality', 'value')])
    def update_quality_refresh_timer(value):
        if UIState.VIEWER_MODE: return 9999999

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
            Quality.add_to_quality(0, "ui", f"Marker {marker_cnt}")
            marker_cnt += 1
            return

        if triggered_id == "graph-bt-save.n_clicks":
            if save is None: return
            DEST = "save.db"
            print("Saving into", DEST, "...")
            DB.save_to_file(DEST)
            print("Saving: done")

            return ""

        if triggered_id == "graph-bt-clear.n_clicks":
            if clear is None: return
            for content in DB.table_contents.values():
                content[:] = []
            DB.quality_by_table .clear()
            print("Cleaned!")
            return

        print("click not handled... ", triggered_id, save, marker, clear)
        return ""

    @UIState.app.callback(Output("cfg:graph:value", 'children'),
                          [Input('cfg:graph', 'value'), Input('graph-bt-stop', 'n_clicks')])
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
                          [Input('cfg:graph', 'value'),
                           Input('graph-bt-stop', 'n_clicks')])
    def update_graph_refresh_timer(value, bt_n_click):
        if UIState.VIEWER_MODE: return 99999

        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        if triggered_id == "graph-bt-stop.n_clicks":
            if bt_n_click is not None and bt_n_click % 2:
                value = 9999

        # from the slider, min = 1
        value += 1

        return [value * 1000 for _ in outputs]
