import dash
from dash.dependencies import Output, Input, State
import dash_html_components as html
from collections import defaultdict

from . import InitialState, UIState

pipeline_cnt = defaultdict(int)

def g_strcompress(string):
    """ Python version of glib::g_strcompress

    Replaces all escaped characters with their one byte equivalent.
    This function does the reverse conversion of g_strescape().
    # https://github.com/GNOME/glib/blob/3dec72b946a527f4b1f35262bddd4afb060409b7/glib/gstrfuncs.c#L2087
    """
    ESCAPE = {'\\':'\\',
              'b': '\b',
              'f':'\f',
              'n': '\n',
              'r':'\r',
              't':'\t',
              'v':'\v',
              '"':'"'}
    string = string.replace("\\342\\200\\246", "…") # unicode is hard ...
    escape_next = False
    new_string = ""
    for c in string:
        if not escape_next and c == "\\":
            escape_next = True
            continue

        if escape_next:
            try:
                c = ESCAPE[c]
            except KeyError:
                print(f"WARNING: Could not escape '\{c}'")
                pass
            escape_next = False
        new_string += c
    return new_string

class Quality():
    @staticmethod
    def add_to_quality(ts, src, msg):
        if msg.startswith("#pipeline:"):
            dest = f"/tmp/pipeline.{src}-{pipeline_cnt[src]}.dot"
            pipeline_cnt[src] += 1

            pipeline_escaped = msg[len("#pipeline:"):]
            with open(dest+".raw", "w") as pipe_out:
                pipe_out.write(pipeline_escaped)

            pipeline = g_strcompress(pipeline_escaped)


            with open(dest, "w") as pipe_out:
                pipe_out.write(pipeline)

            msg = f"<pipeline definition saved into {dest}>"
            print(msg)

        if msg.startswith("#"):
            short = msg[:] + "..."
            UIState().DB.quality.insert(0, (ts, src, short))
        else:
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
    @UIState.app.callback(Output("quality-box", 'children'),
                          [Input('quality-refresh', 'n_intervals')])
    def refresh_quality(*args):
        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

        return [html.P(f"{src}: {msg}", style={"margin-top": "0px", "margin-bottom": "0px"}) \
                for (ts, src, msg) in UIState().DB.quality]

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
