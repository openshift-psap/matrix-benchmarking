import dash
from dash.dependencies import Output, Input, State
import dash_html_components as html

from . import InitialState, UIState

class Quality():
    @staticmethod
    def add_to_quality(ts, src, msg):
        UIState().DB.quality.insert(0, (ts, src, msg))

        if msg.startswith("!"):
            Quality.add_quality_to_plots(msg)

    @staticmethod
    def add_quality_to_plots(msg):
        for table, content in UIState().DB.table_contents.items():
            if not content: continue

            UIState().DB.quality_by_table[table].append((content[-1], msg))

    @staticmethod
    def clear():
        UIState().DB.quality[:] = []

def construct_quality_callbacks():
    refresh_inputs = Input('empty', 'value') if UIState.viewer_mode else \
                     Input('quality-refresh', 'n_intervals')
    @UIState.app.callback(Output("quality-box", 'children'),
                          [refresh_inputs])
    def refresh_quality(*args):
        return [html.P(f"{src}: {msg}", style={"margin-top": "0px", "margin-bottom": "0px"}) \
                for (ts, src, msg) in UIState().DB.quality]

    if UIState.viewer_mode: return

    @UIState.app.callback(Output("quality-refresh", 'n_intervals'),
                          [Input('quality-bt-clear', 'n_clicks'),
                           Input('quality-bt-refresh', 'n_clicks')])
    def clear_quality(clear_n_clicks, refresh_n_clicks):

        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

        if triggered_id == "quality-bt-clear.n_clicks":
            if clear_n_clicks is None: return

            Quality.clear()
        else:
            if refresh_n_clicks is None: return
            # forced refresh, nothing to do

        return 0

    @UIState.app.callback(Output("quality-input", 'value'),
                  [Input('quality-bt-send', 'n_clicks'),
                   Input('quality-input', 'n_submit'),],
                  [State(component_id='quality-input', component_property='value')])
    def quality_send(n_click, n_submit, quality_value):
        if not quality_value:
            return ""

        if not UIState().DB.expe:
            return "<error: expe not set>"
        UIState().DB.expe.send_quality(quality_value)

        return "" # empty the input text
