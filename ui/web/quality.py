import dash
from dash.dependencies import Output, Input, State
import dash_html_components as html
import dash_core_components as dcc
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
        db = UIState().DB
        db.quality.insert(0, (ts, src, msg))

        if msg.startswith("#pipeline:"):
            db.pipelines[msg] = db.pipeline_idx
            db.pipelines_reversed[db.pipeline_idx] = msg
            db.pipeline_idx += 1

        if msg.startswith("!"):
            Quality.add_quality_to_plots(msg)

    @staticmethod
    def add_quality_to_plots(msg):
        db = UIState().DB

        for table, content in db.table_contents.items():
            if not content: continue

            db.quality_by_table[table].append((content[-1], msg))

    @staticmethod
    def clear():
        UIState().DB.quality[:] = []

def get_pipeline(db, idx, ext, raw=False):
    pipeline_escaped = db.pipelines_reversed[int(idx)]

    pipeline = g_strcompress(pipeline_escaped[len("#pipeline:"):])

    if pipeline == "too long":
        return "ERROR: pipeline data was too long for the client-server channel..."

    if ext == "dot":
        if raw: return 'text/plain', pipeline

        return dcc.Textarea(value=pipeline,
                            style=dict(width='100%', height='100vh'))

    from subprocess import Popen, PIPE
    import base64

    p = Popen(['dot', '-Tpng'], stdin=PIPE, stdout=PIPE)
    p.stdin.write(pipeline.encode('ascii'))
    p.stdin.close()

    data = p.stdout.read()
    if raw: return 'image/png', data

    b64_data = base64.b64encode(data).decode('ascii')

    return html.Img(src='data:image/png;base64,'+b64_data)


def construct_quality_callbacks(url=None):
    @UIState.app.server.route('/collector/pipeline/<idx>.<ext>')
    def download_pipeline(idx, ext):
        db = UIState().DB
        if not db.pipelines:
            return "No pipeline available, is the app initialized?"

        try:
            mimetype, data = get_pipeline(db, int(idx), ext, raw=True)

            import flask
            return flask.Response(data, mimetype=mimetype)
        except Exception as e:
            return str(e)

    @UIState.app.callback(Output("quality-box", 'children'),
                          [Input('quality-refresh', 'n_intervals')])
    def refresh_quality(*args):
        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)
        db = UIState().DB
        quality_html = []
        for (ts, src, msg) in db.quality:
            if msg.startswith("#pipeline:"):
                pipeline_idx = db.pipelines[msg]
                link = f"/{UIState().url}/pipeline/{pipeline_idx}"
                children = [src, f": Pipeline #{pipeline_idx}  ({len(msg)} chars) ",
                            html.A("[dot]", target="_blank", href=link+".dot"),
                            " ",
                            html.A("[png]", target="_blank", href=link+".png"),
                            ]
            else:
                children = f"{src}: {msg}"
            quality_html.append(html.P(children, style={"margin-top": "0px", "margin-bottom": "0px"}))

        return quality_html


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
