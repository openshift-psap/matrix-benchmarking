from collections import defaultdict
import importlib

import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html

from . import InitialState, UIState
from . import feedback

control_center_boxes = defaultdict(list)

plugin_control = None

def configure(mode, plugin_cfg, machines):
    global plugin_control

    plugin_pkg_name = f"plugins.{mode}.control"

    try: plugin_control = importlib.import_module(plugin_pkg_name)
    except Exception as e:
        print(f"ERROR: Cannot load control plugin package ({plugin_pkg_name}) ...")
        raise e

    plugin_control.configure(plugin_cfg, machines)

def apply_settings(driver_name, settings):
    settings_str = ",".join(f"{k}={v}" for k, v in settings.items() if v not in (None, ""))

    feedback.Feedback.add_to_feedback(None, "ui", f"Apply settings: {driver_name} || {settings_str}")

    err = plugin_control.apply_settings(driver_name, settings)
    if not err:
        return f"settings applied: {driver_name} || {settings_str}"

    msg = f"FAILED ({err})"
    feedback.Feedback.add_to_feedback(None, "ui", f"Apply settings: {msg}")

    return msg

def reset_settings():
    plugin_control.reset_settings()

def request(msg, dry, log, **kwargs):
    return plugin_control.request(msg, dry, log, **kwargs)

def construct_driver_control_callback(driver_name):
    driver_id_name = driver_name.replace(".", ":")
    cb_states = [State(tag_id, tag_cb_field) \
                 for tag_id, tag_cb_field, *_ in control_center_boxes[driver_name]]

    setting_names = [tag_id.rpartition(":")[-1]
                   for tag_id, tag_cb_field, _ in control_center_boxes[driver_name]]
    @UIState.app.callback(Output(f"{driver_id_name}-msg", 'children'),
                          [Input(f'{driver_id_name}-go-button', "n_clicks"),
                           Input(f'{driver_id_name}-reset-button', "n_clicks")],
                           cb_states)
    def activate_driver(*args):

        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

        go_n_clicks, reset_n_clicks, *states = args

        if triggered_id == f"{driver_id_name}-reset-button.n_clicks":
            if reset_n_clicks is None: return # button creation

            reset_settings()
            return "Encoding reset!"

        if go_n_clicks is None: return # button creation

        settings = dict(zip(setting_names, states))
        if settings.get("custom", None):
            for custom in settings["custom"].split(";"):
                k, _, v = custom.partition("=")
                settings[k] = v

            del settings["custom"]

        return apply_settings(driver_name, settings)

    for tag_id, tag_cb_field, need_value_cb in control_center_boxes[driver_name]:
        if not need_value_cb: continue

        @UIState.app.callback(Output(f"{tag_id}:value", 'children'),
                               [Input(tag_id, tag_cb_field)])
        def value_callback(value):
            return f": {value if value is not None else ''}"


def construct_driver_control_callbacks(driver_cfg):
    for driver_name, options in driver_cfg.items():
        if not options: options = {}
        if options.get("_group") is True: continue
        if options.get("_disabled"): continue

        construct_driver_control_callback(driver_name)

def construct_control_center_tab(driver_cfg):

    def get_option_box(driver_name, opt_name, opt_props):
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

        tag_id = f"{driver_name}-opt:{opt_name.lower()}".replace(".", "_")
        tag.id = tag_id

        control_center_boxes[driver_name].append((tag_id, tag_cb_field, need_value_cb))

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

    def get_driver_params(driver_name, driver_id_name):
        all_options = {}
        for name, options in driver_cfg.items():
            if not options: continue
            if "_disabled" in options: continue

            if driver_name == name: pass # keep
            elif name == "_all": pass # keep
            elif options.get("_group") is True:
                driver_opts = driver_cfg.get(driver_name)
                if not driver_opts: continue
                group = driver_opts.get("_group")
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
            yield from get_option_box(driver_name, opt_name, opt_props)

        yield from get_option_box(driver_name, "custom", {"desc": "format: (key=value;)*"})

        yield html.P(id=f"{driver_id_name}-msg", style={"text-align":"center"})

    def get_driver_tabs():
        for driver_name, options in driver_cfg.items():
            if options is None: options = {}

            if options.get("_group") is True: continue
            if options.get("_disabled"): continue

            print(f"Create {driver_name} tab ...")
            driver_id_name = driver_name.replace(".", ":")
            children = []
            children += [html.Div([html.Button('Go!', id=f'{driver_id_name}-go-button'),
                                   html.Button('Reset', id=f'{driver_id_name}-reset-button')],
                                  style={"text-align": "center"})]
            children += get_driver_params(driver_name, driver_id_name)

            yield dcc.Tab(label=driver_name, children=children)

    driver_tabs = [
        html.H3("Drivers & settings", style={"text-align":"center"}),
        dcc.Tabs(id="driver-settings-tabs", children=list(get_driver_tabs())),
    ]

    refresh_interval = 9999999 if UIState().viewer_mode else InitialState.FEEDBACK_REFRESH_INTERVAL * 1000

    feedback_headers = [html.H3("Feedback Messages", style={"text-align":"center"}),
                       dcc.Interval(
                           id='feedback-refresh', n_intervals=0,
                           interval=refresh_interval
                       )]

    feedback_area = html.Div(id="feedback-box", children=[],
                            style={"margin-top": "10px", "margin-left": "0px",
                                   "padding-left": "10px", "padding-top": "10px",
                                   "background-color": "lightblue", "text-align":"left",})

    if UIState().viewer_mode:
        tab_children = feedback_headers + [feedback_area]
    else:
        feedback_children = feedback_headers + [
            dcc.Input(placeholder='Enter a feedback message...', type='text', value='', id="feedback-input"),
            html.Button('Send!', id='feedback-bt-send'),
            html.Button('Clear', id='feedback-bt-clear'),
            html.Button('Refresh', id='feedback-bt-refresh'),
            html.Br(),
            "Refreshing feedback ", html.Span(id="cfg:feedback:value"),
            dcc.Slider(min=0, max=30, step=1, value=InitialState.FEEDBACK_REFRESH_INTERVAL,
                       marks={0:"0s", 30:"30s"},
                       id="cfg:feedback"), html.Br(),
            feedback_area]

        tab_children = [
            html.Div([
                html.Div(feedback_children, style={"text-align":"center",}, className="four columns"),
                html.Div(driver_tabs, className="eight columns"),
            ], className="row")
        ]

    return dcc.Tab(label="Control center", children=tab_children)
