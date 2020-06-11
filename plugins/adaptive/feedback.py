from collections import defaultdict

import dash_html_components as html
import dash_core_components as dcc

import ui
import ui.feedback

pipeline_cnt = defaultdict(int)

def init_db(db):
    db.pipeline_idx = 0
    db.pipelines = {} # pipeline -> id
    db.pipelines_reversed = {} # id -> pipeline

def handle_new_feedback(msg, db):
    if msg.startswith("!"):
        ui.feedback.Feedback.add_feedback_to_plots(msg)
        return

    if msg.startswith("#pipeline:"):
        db.pipelines[msg] = db.pipeline_idx
        db.pipelines_reversed[db.pipeline_idx] = msg
        db.pipeline_idx += 1

def handle_viewer_req(ui_states, key, args):
    if not args.startswith("pipeline/"):
        return False

    try: db = ui_states[key].DB
    except KeyError: return html.Div(f"Error: key '{key}' not found, is the viewer loaded?")
    idx, _, ext = args.partition("/")[-1].partition(".")

    return generate_pipeline(db, int(idx), ext)


def construct_collector_callbacks(app):
    @app.server.route('/collector/pipeline/<idx>.<ext>')
    def download_pipeline(idx, ext):
        db = ui.UIState().DB

        if not db.pipelines:
            return "No pipeline available, is the app initialized?"

        try:
            mimetype, data = generate_pipeline(db, int(idx), ext, raw=True)

            import flask
            return flask.Response(data, mimetype=mimetype)
        except Exception as e:
            return str(e)

def process_feedback(ts, src, msg, db):
    if not msg.startswith("#pipeline:"):
        return False

    pipeline_idx = db.pipelines[msg]
    link = f"/{ui.UIState().url}/pipeline/{pipeline_idx}"

    return [src, f": Pipeline #{pipeline_idx}  ({len(msg)} chars) ",
            html.A("[dot]", target="_blank", href=link+".dot"),
            " ",
            html.A("[png]", target="_blank", href=link+".png"),
    ]

# ---- #
# -  - #
# ---- #

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

def generate_pipeline(db, idx, ext, raw=False):
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
    p.stdin.write(pipeline.encode('utf-8'))
    p.stdin.close()

    data = p.stdout.read()
    if raw: return 'image/png', data

    b64_data = base64.b64encode(data).decode('ascii')

    return html.Img(src='data:image/png;base64,'+b64_data)
