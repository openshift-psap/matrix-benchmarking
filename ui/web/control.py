from collections import defaultdict
import json
import os
import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html
import socket

from . import InitialState, UIState
from . import quality

control_center_boxes = defaultdict(list)

USE_VIRSH = None
VIRSH_VM_NAME = None
QMP_ADDR = None

def send_qmp(set_spice_args):
    json_msg = json.dumps(dict(execute="set-spice",
                               arguments=set_spice_args))

    if USE_VIRSH:
        cmd = f"virsh qemu-monitor-command {VIRSH_VM_NAME} '{json_msg}'"
        os.system(cmd)
        return

    qmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    qmp_sock.connect(QMP_ADDR)
    qmp_sock.send('{"execute":"qmp_capabilities"}'.encode('ascii'))
    qmp_sock.send(json_msg.encode("ascii"))
    resp = ""
    to_read = 3
    while True:
        c = qmp_sock.recv(1).decode('ascii')
        if not c: break
        resp += c

        if c == '\n':
            if "error" in resp:
                print(resp)
            to_read -= 1; resp = ""
            if to_read == 0: break
    del qmp_sock

def set_encoder(encoder_name, parameters):
    params_str = ",".join(f"{k}={v}" for k, v in parameters.items() if v not in (None, ""))

    args = {"guest-encoder": encoder_name,
            "guest-encoder-params": params_str}
    try:
        args["target-fps"] = int(parameters["framerate"])
    except KeyError: pass # no framerate available, ignore
    except ValueError as e:
        print("WARNING: invalid value for 'framerate':", e)

    send_qmp(set_spice_args=args)

    quality.Quality.add_to_quality(None, "ui", f"Set encoder: {encoder_name} || {params_str}")

    return f"{encoder_name} || {params_str}"

def construct_codec_control_callback(codec_name):
    codec_id_name = codec_name.replace(".", ":")
    cb_states = [State(tag_id, tag_cb_field) \
                 for tag_id, tag_cb_field, *_ in control_center_boxes[codec_name]]

    param_names = [tag_id.rpartition(":")[-1]
                   for tag_id, tag_cb_field, _ in control_center_boxes[codec_name]]
    @UIState.app.callback(Output(f"{codec_id_name}-msg", 'children'),
                           [Input(f'{codec_id_name}-go-button', "n_clicks"),
                            Input(f'{codec_id_name}-reset-button', "n_clicks")],
                           cb_states)
    def activate_codec(*args):

        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

        go_n_clicks, reset_n_clicks, *states = args

        if triggered_id == f"{codec_id_name}-reset-button.n_clicks":
            if reset_n_clicks is None: return # button creation

            set_encoder("reset", {})
            return "Encoding reset!"

        if go_n_clicks is None: return # button creation

        params = dict(zip(param_names, states))
        if params.get("custom", None):
            for custom in params["custom"].split(";"):
                k, _, v = custom.partition("=")
                params[k] = v

            del params["custom"]

        return set_encoder(codec_name, params)

    for tag_id, tag_cb_field, need_value_cb in control_center_boxes[codec_name]:
        if not need_value_cb: continue

        @UIState.app.callback(Output(f"{tag_id}:value", 'children'),
                               [Input(tag_id, tag_cb_field)])
        def value_callback(value):
            return f": {value if value is not None else ''}"


def construct_codec_control_callbacks(codec_cfg):
    for codec_name, options in codec_cfg.items():
        if not options: options = {}
        if options.get("_group") is True: continue
        if options.get("_disabled"): continue

        construct_codec_control_callback(codec_name)

def construct_control_center_tab(codec_cfg):

    def get_option_box(codec_name, opt_name, opt_props):
        tag = None
        tag_cb_field = "value"
        need_value_cb = False
        opt_type = opt_props.get("type", "str")
        default = opt_props.get("default")
        default_str = f" | default: {default}" if default is not None else ""

        if opt_type.startswith("int["): # int[start:end:step]
            _min, _max, _step = map(int, opt_type[4:-1].split(":"))
            marks = {_min:_min, _max:_max}
            if default is None: default = 0

            tag = dcc.Slider(min=_min, max=_max, step=_step, value=int(default), marks=marks)
            need_value_cb = True

        elif opt_type in ("int", "uint", "float", "ufloat"):

            tag = dcc.Input(placeholder=f'Enter a numeric value for "{opt_name}"'+default_str,
                                    type='number', style={"width": "100%"})
            need_value_cb = False

        elif opt_type == "enum":
            options = [{'label': enum, 'value': enum} for enum in [""] + opt_props['values'].split(", ")]

            tag = dcc.Dropdown(options=options,
                               placeholder=f'Enter a value for "{opt_name}"'+default_str,
                               searchable=False)

        if tag is None:
            if opt_type != "str":
                raise Exception(f"Option not handled ... {opt_name}->{opt_props}")

            tag = dcc.Input(placeholder=f'Enter a value for "{opt_name}"'+default_str,
                            type='text', style={"width": "100%"})

        tag_id = f"{codec_name}-opt:{opt_name.lower()}".replace(".", "_")
        tag.id = tag_id

        control_center_boxes[codec_name].append((tag_id, tag_cb_field, need_value_cb))

        opt_name_span = html.Span(opt_name)
        children = [opt_name_span, html.Span(id=tag_id+":value")]

        opt_name_span.title = ""

        opt_name_span.title += opt_props.get("desc", "")
        if "default" in opt_props:
            opt_name_span.title += f' [default: {opt_props["default"]}]'

        try:
            url = opt_props["url"]
            children.append(html.A("*", href=url, target="_blank", title=f"More about {opt_name}"))
        except KeyError: pass

        return [html.P(children=children, style={"text-align": "center"}),
                html.P([tag])]

    def get_codec_params(codec_name, codec_id_name):
        all_options = {}
        for name, options in codec_cfg.items():
            if not options: continue
            if "_disabled" in options: continue

            if codec_name == name: pass # keep
            elif name == "_all": pass # keep
            elif options.get("_group") is True:
                codec_opts = codec_cfg.get(codec_name)
                if not codec_opts: continue
                group = codec_opts.get("_group")
                try:
                    if group != name and name not in group:
                        continue
                    # else: keep
                except TypeError: continue # argument of type 'bool' is not iterable

            else: continue

            if "_group" in options:
                options = options.copy()
                del options["_group"]

            all_options.update(options)

        for opt_name, opt_props in all_options.items():
            if opt_name.startswith("_"): continue
            yield from get_option_box(codec_name, opt_name, opt_props)

        yield from get_option_box(codec_name, "custom", {"desc": "format: (key=value;)*"})

        yield html.P(id=f"{codec_id_name}-msg", style={"text-align":"center"})

    def get_codec_tabs():
        for codec_name, options in codec_cfg.items():
            if options is None: options = {}

            if options.get("_group") is True: continue
            if options.get("_disabled"): continue

            print(f"Create {codec_name} tab ...")
            codec_id_name = codec_name.replace(".", ":")
            children = []
            children += [html.Div([html.Button('Go!', id=f'{codec_id_name}-go-button'),
                                   html.Button('Reset', id=f'{codec_id_name}-reset-button')],
                                  style={"text-align": "center"})]
            children += get_codec_params(codec_name, codec_id_name)

            yield dcc.Tab(label=codec_name, children=children)

    codec_tabs = [
        html.H3("Video Encoding", style={"text-align":"center"}),
        dcc.Tabs(id="video-enc-tabs", children=list(get_codec_tabs())),
    ]

    refresh_interval = 9999999 if UIState().viewer_mode else InitialState.QUALITY_REFRESH_INTERVAL * 1000

    quality_headers = [html.H3("Quality Messages", style={"text-align":"center"}),
                       dcc.Interval(
                           id='quality-refresh', n_intervals=0,
                           interval=refresh_interval
                       )]

    quality_area = html.Div(id="quality-box", children=[],
                            style={"margin-top": "10px", "margin-left": "0px",
                                   "padding-left": "10px", "padding-top": "10px",
                                   "background-color": "lightblue", "text-align":"left",})

    if UIState().viewer_mode:
        tab_children = quality_headers + [quality_area]
    else:
        quality_children = quality_headers + [
            dcc.Input(placeholder='Enter a quality message...', type='text', value='', id="quality-input"),
            html.Button('Send!', id='quality-bt-send'),
            html.Button('Clear', id='quality-bt-clear'),
            html.Button('Refresh', id='quality-bt-refresh'),
            html.Br(),
            "Refreshing quality ", html.Span(id="cfg:quality:value"),
            dcc.Slider(min=0, max=30, step=1, value=InitialState.QUALITY_REFRESH_INTERVAL,
                       marks={0:"0s", 30:"30s"},
                       id="cfg:quality"), html.Br(),
            quality_area]

        tab_children = [
            html.Div([
                html.Div(quality_children, style={"text-align":"center",}, className="four columns"),
                html.Div(codec_tabs, className="eight columns"),
            ], className="row")
        ]

    return dcc.Tab(label="Control center", children=tab_children)
