from collections import defaultdict
import json
import os
import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html

from . import InitialState, UIState
from . import quality

control_center_boxes = defaultdict(list)

VIRSH_VM_NAME = "fedora30"

def set_encoder(encoder_name, parameters):
    params_str = ";".join(f"{name+'=' if not name.startswith('_') else ''}{value}" for name, value in parameters.items() if value not in (None, "")) + ";"
    json_msg = json.dumps(dict(execute="set-spice",
                               arguments={"guest-encoder": encoder_name,
                                          "guest-encoder-params": params_str}))

    cmd = f"virsh qemu-monitor-command {VIRSH_VM_NAME} '{json_msg}'"
    os.system(cmd)

    quality.Quality.add_to_quality(None, "ui", f"Set encoder: {encoder_name} || {params_str}")

    return f"{encoder_name} || {params_str}"

def construct_codec_control_callback(codec_name):
    if UIState.VIEWER_MODE: return

    cb_states = [State(tag_id, tag_cb_field) \
                 for tag_id, tag_cb_field, *_ in control_center_boxes[codec_name]]

    param_names = [prefix+tag_id.rpartition(":")[-1]
                   for tag_id, tag_cb_field, _, prefix in control_center_boxes[codec_name]]
    @UIState.app.callback(Output(f"{codec_name}-msg", 'children'),
                          [Input(f'{codec_name}-go-button', "n_clicks"),
                           Input(f'{codec_name}-reset-button', "n_clicks")],
                          cb_states)
    def activate_codec(*args):
        triggered_id = dash.callback_context.triggered[0]["prop_id"]

        go_n_clicks, reset_n_clicks, *states = args

        if triggered_id == f"{codec_name}-reset-button.n_clicks":
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

    for tag_id, tag_cb_field, need_value_cb, _ in control_center_boxes[codec_name]:
        if not need_value_cb: continue

        @UIState.app.callback(Output(f"{tag_id}:value", 'children'),
                              [Input(tag_id, tag_cb_field)])
        def value_callback(value):
            return f": {value if value is not None else ''}"


def construct_codec_control_callbacks(codec_cfg):
    for codec_name, options in codec_cfg.items():
        if codec_name.startswith("_"): continue
        if options and "_disabled" in options: continue

        construct_codec_control_callback(codec_name)

def construct_control_center_tab(codec_cfg):

    def get_option_box(codec_name, opt_name, opt_props):
        tag = None
        tag_cb_field = "value"
        need_value_cb = False
        opt_type = opt_props.get("type", "str")

        if opt_type.startswith("int["): # int[start:end:step]=default
            range_str, _, default = opt_type[4:].partition("]=")
            _min, _max, _step = map(int, range_str.split(":"))
            marks = {_min:_min, _max:_max}
            tag = dcc.Slider(min=_min, max=_max, step=_step, value=int(default), marks=marks)
            need_value_cb = True
        elif opt_type.startswith("int"):
            default = int(opt_type.partition("=")[-1]) if opt_type.startswith("int=") else ""

            tag = dcc.Input(placeholder=f'Enter a numeric value for "{opt_name}"',
                                    type='number', value=default, style={"width": "100%"})
            need_value_cb = True

        elif opt_type == "enum":
            options = [{'label': enum, 'value': enum} for enum in [""] + opt_props['values'].split(", ")]
            tag = dcc.Dropdown(options=options, searchable=False)

        if tag is None:
            if opt_type != "str":
                raise Exception(f"Option not handled ... {opt_name}->{opt_props}")

            tag = dcc.Input(placeholder=f'Enter a value for "{opt_name}"', type='text',
                            style={"width": "100%"})

        tag_id = f"{codec_name}-opt:{opt_name.lower()}".replace(".", "_")
        tag.id = tag_id

        prefix = opt_props.get("_prefix", "")
        control_center_boxes[codec_name].append((tag_id, tag_cb_field, need_value_cb, prefix))

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

    def get_codec_params(codec_name):
        all_options = {}
        for name, options in codec_cfg.items():
            if not options: continue

            if name == "_all" or name.startswith("_") and codec_name.startswith(name[1:]): pass # keep
            elif codec_name == name: pass # keep
            else: continue

            if "_prefix" in options:
                prefix = options["_prefix"]
                options = options.copy()
                del options["_prefix"]
                for param_option in options.values():
                    param_option["_prefix"] = prefix

            all_options.update(options)

        for opt_name, opt_props in all_options.items():
            yield from get_option_box(codec_name, opt_name, opt_props)

        yield from get_option_box(codec_name, "custom", {"desc": "format: (key=value;)*"})

        yield html.P(id=f"{codec_name}-msg", style={"text-align":"center"})

    def get_codec_tabs():
        for codec_name, options in codec_cfg.items():
            if codec_name.startswith("_"): continue

            if options is None: options = {}

            if "_disabled" in options: continue

            print(f"Create {codec_name} tab ...")
            children = []
            children += [html.Div([html.Button('Go!', id=f'{codec_name}-go-button'),
                                   html.Button('Reset', id=f'{codec_name}-reset-button')],
                                  style={"text-align": "center"})]
            children += get_codec_params(codec_name)

            yield dcc.Tab(label=codec_name, children=children)

    codec_tabs = [
        html.H3("Video Encoding", style={"text-align":"center"}),
        dcc.Tabs(id="video-enc-tabs", children=list(get_codec_tabs())),
    ]

    quality_header = html.H3("Quality Messages", style={"text-align":"center"})

    quality_area = html.Div(id="quality-box", children=[],
                            style={"margin-top": "10px", "margin-left": "0px",
                                   "padding-left": "10px", "padding-top": "10px",
                                   "background-color": "lightblue", "text-align":"left",})

    if UIState.VIEWER_MODE:
        tab_children = [quality_header, quality_area]
    else:
        quality_children = [
            quality_header,
            dcc.Interval(
                id='quality-refresh',
                interval=InitialState.QUALITY_REFRESH_INTERVAL * 1000
            ),
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
