from collections import defaultdict
import importlib

import dash
from dash.dependencies import Output, Input, State
import dash_html_components as html
import dash_core_components as dcc

from . import InitialState, UIState

plugin = None

def configure(mode):
    global plugin
    plugin_pkg_name = f"plugins.{mode}.feedback"
    try: plugin = importlib.import_module(plugin_pkg_name)
    except ModuleNotFoundError:
        return
    except Exception as e:
        print(f"ERROR: Cannot load control plugin package ({plugin_pkg_name}) ...")
        raise e

class Feedback():
    @staticmethod
    def add_to_feedback(ts, src, msg):
        db = UIState().DB
        db.feedback.insert(0, (ts, src, msg))

        plugin.handle_new_feedback(msg, db)

    @staticmethod
    def add_feedback_to_plots(msg):
        db = UIState().DB

        for table, content in db.table_contents.items():
            if not content: continue

            db.feedback_by_table[table].append((content[-1], msg))

    @staticmethod
    def clear():
        UIState().DB.feedback[:] = []

def construct_feedback_callbacks(url=None):
    if not plugin: return

    plugin.construct_collector_callbacks(UIState.app)

    @UIState.app.callback(Output("feedback-box", 'children'),
                          [Input('feedback-refresh', 'n_intervals')])
    def refresh_feedback(*args):
        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)
        db = UIState().DB
        feedback_html = []
        for (ts, src, msg) in db.feedback:
            children = plugin.process_feedback(ts, src, msg, db)
            if children is False:
                children = f"{src}: {msg}"

            feedback_html.append(html.P(children,
                                        style={"margin-top": "0px", "margin-bottom": "0px"}))

        return feedback_html


    @UIState.app.callback(Output("feedback-refresh", 'n_intervals'),
                          [Input('feedback-bt-clear', 'n_clicks'),
                           Input('feedback-bt-refresh', 'n_clicks')])
    def clear_feedback(clear_n_clicks, refresh_n_clicks):

        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

        if triggered_id == "feedback-bt-clear.n_clicks":
            if clear_n_clicks is None: return

            Feedback.clear()
        else:
            if refresh_n_clicks is None: return
            # forced refresh, nothing to do

        return 0

    @UIState.app.callback(Output("feedback-input", 'value'),
                  [Input('feedback-bt-send', 'n_clicks'),
                   Input('feedback-input', 'n_submit'),],
                  [State(component_id='feedback-input', component_property='value')])
    def feedback_send(n_click, n_submit, feedback_value):
        if not feedback_value:
            return ""

        if not UIState().DB.expe:
            return "<error: expe not set>"
        UIState().DB.expe.send_feedback(feedback_value)

        return "" # empty the input text
