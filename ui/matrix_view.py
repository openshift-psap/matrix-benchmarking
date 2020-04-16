from collections import defaultdict
import types, importlib
import urllib.parse
import re

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Output, Input, State, ClientsideFunction

import flask

from .table_stats import TableStats

def natural_keys(text):
    def atoi(text): return int(text) if text.isdigit() else text
    return [atoi(c) for c in re.split(r'(\d+)', str(text))]

def join(joiner, iterable):
    i = iter(iterable)
    try:
        yield next(i)  # First value, or StopIteration
        while True:
            next_value = next(i)
            yield joiner
            yield next_value
    except StopIteration: pass

NB_GRAPHS = 3
GRAPH_IDS = [f"graph-{i}" for i in range(NB_GRAPHS)]
TEXT_IDS = [f"graph-{i}-txt" for i in range(NB_GRAPHS)]

def COLORS(idx):
    colors = [
        '#1f77b4',  # muted blue
        '#ff7f0e',  # safety orange
        '#2ca02c',  # cooked asparagus green
        '#d62728',  # brick red
        '#9467bd',  # muted purple
        '#8c564b',  # chestnut brown
        '#e377c2',  # raspberry yogurt pink
        '#7f7f7f',  # middle gray
        '#bcbd22',  # curry yellow-green
        '#17becf'   # blue-teal
    ]
    return colors[idx % len(colors)]

class Matrix():
    properties = defaultdict(set)
    entry_map = {}

    broken_files = []

def parse_data(_):
    raise RuntimeError("matrix_view is not configured ...")

def all_records(_, __):
    raise RuntimeError("matrix_view is not configured ...")

def configure(mode):
    plugins_pkg_name = f"plugins.{mode}.matrix_view"

    try: plot = importlib.import_module(plugins_pkg_name)
    except Exception as e:
        print(f"ERROR: Cannot load matrix plugins package ({plugins_pkg_name}) ...")
        raise e

    global parse_data, all_records

    parse_data = plot.parse_data
    all_records = plot.all_records

    plot.register()

def get_permalink(args, full=False):
    params = dict(zip(Matrix.properties.keys(), args[:len(Matrix.properties)]))

    def val(k, v):
        if isinstance(v, list): return "&".join(f"{k}={vv}" for vv in v)
        else: return f"{k}={v}"

    search = "?"+"&".join(val(k, v) for k, v in params.items() \
                            if v not in ('---', None) and (full or len(Matrix.properties[k]) != 1))
    *_, custom_cfg, custom_cfg_saved, props_order = args
    if props_order:
        search += f"&property-order={props_order}"

    if custom_cfg_saved or custom_cfg:
        lst = custom_cfg_saved[:] if custom_cfg_saved else []
        if custom_cfg and not custom_cfg in lst:
            lst.insert(0, custom_cfg)

        search += ("&" + "&".join([f"cfg={cfg}" for cfg in lst])) if lst else ""

    return search

def build_layout(search, serializing=False):
    defaults = urllib.parse.parse_qs(search[1:]) if search else {}

    matrix_controls = [html.B("Parameters:", id="lbl_params"), html.Br()]
    serial_params = []
    for key, values in Matrix.properties.items():
        options = [{'label': i, 'value': i} for i in sorted(values, key=natural_keys)]

        attr = {}
        if key == "stats":
            attr["multi"] = True

        elif len(values) == 1:
            attr["disabled"] = True
            attr["value"] = options[0]['value']
        else:
            options.insert(0, {'label': "[ all ]", 'value': "---"})
            attr["searchable"] = False

            if key == "experiment" and "current" in values:
                attr["value"] = "current"
            else:
                attr["value"] = "---"

        try:
            default_value = defaults[key]
            attr["value"] = default_value[0] if len(default_value) == 1 else default_value
        except KeyError: pass

        if serializing:
            attr["disabled"] = True
            serial_params.append(attr["value"])

        tag = dcc.Dropdown(id='list-params-'+key, options=options,
                           **attr, clearable=False)

        matrix_controls += [html.Span(f"{key}: ", id=f"label_{key}"), tag]


    cfg_data = defaults.get('cfg', [])
    cfg_children = list([html.P(e) for e in cfg_data])

    config = [html.B("Configuration:", id='config-title'), html.Br(),
              dcc.Input(id='custom-config', placeholder='Config settings', debounce=True),
              html.Div(id='custom-config-saved', children=cfg_children, **{'data-label': cfg_data})]

    aspect = [html.Div(defaults.get("property-order", [''])[0], id='property-order')]

    permalink = [html.P(html.A('Permalink', href='', id='permalink'))]
    download = [html.P(html.A('Download', href='', id='download', target="_blank"))]

    control_children = matrix_controls

    if not serializing:
        control_children += config + aspect + permalink + download
    else:
        control_children += [html.I(["Saved on ",
                                    str(datetime.datetime.today()).rpartition(":")[0]])]

        permalink = "/matrix/"+get_permalink((
            serial_params # [Input('list-params-'+key, "value") for key in Matrix.properties]
            + [''] # custom-config useless here
            + [cfg_data]
            + [defaults.get("property-order", [''])[0]]
        ), full=True)

        control_children += [html.P(["from ",
                                     html.A("this page", target="_blank", href=permalink),
                                     "."])]

    graph_children = []
    if serializing:
        stats = defaults.get("stats", [])
        for stats_name in stats:
            print("Generate", stats_name)
            table_stat = TableStats.stats_by_name[stats_name]

            graph_children += [dcc.Graph(id=table_stat.id_name, style={},
                                         config=dict(showTips=False)),
                               html.P(id=table_stat.id_name+'-txt')]

            figure_text = TableStats.graph_figure(*(
                serial_params                          # [Input('list-params-'+key, "value") for key in Matrix.properties]
                + [0]                                  # Input("lbl_params", "n_clicks")
                + defaults.get("property-order", ['']) # Input('property-order', 'children')
                + [None]                               # Input('config-title', 'n_clicks') | None->not clicked yet
                + ['']                                 # Input('custom-config', 'value')
                + ['']                                 # Input('custom-config-saved', 'data')
                + [defaults.get("cfg", [''])]          # State('custom-config-saved', 'data-label')
            ))

            graph, text = graph_children[-2:]
            graph.figure = figure_text[0]
            graph.style['height'] = '100vh'
            graph.style["height"] = f"{100/(min(NB_GRAPHS, len(stats))):.2f}vh"
            if not graph.figure:
                graph.style['display'] = 'none'

            text.children = figure_text[1]
    else:
        for graph_id in GRAPH_IDS:
            graph_children += [dcc.Graph(id=graph_id, style={'display': 'none'},
                                         config=dict(showTips=False)),
                               html.P(id=graph_id+"-txt")]

    graph_children += [html.Div(id="text-box:clientside-output")]

    return html.Div([
        html.Div(children=control_children, className='two columns'),
        html.Div(children=graph_children, id='graph-box', className='ten columns'),
        html.P(id="graph-hover-info"),
    ])

# currently not used, kept for reference ...
def treat_invalids():
    invalids = [html.B("Invalids:"), html.Br(),
                html.Button("Show", id="invalids-show"),
                html.Button("Delete", id="invalids-delete")]

    @app.callback([Input('invalids-show', 'n_clicks'), Input('invalids-delete', 'n_clicks')])
    def do():
        if triggered_id.startswith("invalids-show"):
            return ([html.P(html.B(f"Found {len(Matrix.broken_files)} invalid record files:"))]
                    +[html.P(f"{fname} | {msg}") for fname, msg in Matrix.broken_files])

        if triggered_id.startswith("invalids-delete"):
            ret = []
            for fname, msg in Matrix.broken_files:
                try:
                    import os
                    os.unlink(fname)
                    ret += [html.P(f"{fname}: Deleted")]
                except Exception as e:
                    ret += [html.P(html.B(f"{fname}: Failed: {e}"))]
            Matrix.broken_files[:] = []
            return ret + [html.P(html.B("Local matrix state cleaned up."))]

def build_callbacks(app):
    if not Matrix.properties:
        print("WARNING: Matrix empty, cannot build its GUI")
        return

    print("---")
    for key, values in Matrix.properties.items():
        if key == "stats": continue
        Matrix.properties[key] = sorted(values, key=natural_keys)
        print(f"{key:20s}: {', '.join(map(str, Matrix.properties[key]))}")
    print("---")

    @app.server.route('/matrix/dl')
    def download_graph():
        search = (b"?"+flask.request.query_string).decode('ascii')
        layout = build_layout(search, serializing=True)

        import dill
        data = dill.dumps(layout)
        query = urllib.parse.parse_qs(search[1:])

        fname = '__'.join(TableStats.stats_by_name[stat_name].id_name
                          for stat_name in query['stats']) \
                              if query.get('stats') else "nothing"

        resp = flask.Response(data, mimetype="application/octet-stream")
        resp.headers["Content-Disposition"] = f'attachment; filename="{fname}.dill"'

        return resp

    app.clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="resize_graph"),
        Output("text-box:clientside-output", "children"),
        [Input('permalink', "href"), Input('list-params-stats', "value")],
    )

    @app.callback([Output('custom-config-saved', 'children'),
                   Output('custom-config-saved', 'data'),
                   Output('custom-config', 'value')],
                  [Input('config-title', 'n_clicks')],
                  [State('custom-config-saved', 'data'),
                   State('custom-config', 'value')])
    def save_config(*args):
        title_click, data, value = args
        if data is None: data = []

        if not value:
            return dash.no_update, dash.no_update, ''
        if value in data:
            return dash.no_update, dash.no_update, ''

        if value.startswith("_"):
            if value[1:] not in data:
                print(f"WARNING: tried to remove '{value[1:]}' but it's not in '{', '.join(data)}'")
                return dash.no_update, dash.no_update, dash.no_update
            data.remove(value[1:])
        else:
            k, _, v = value.partition("=")

            for d in data[:]:
                if d.startswith(k + "="): data.remove(d)
            if v:
                data.append(value)

        return list([html.P(e) for e in data]), data, ''

    @app.callback(Output('property-order', 'children'),
                  [Input(f"label_{key}", 'n_clicks') for key in Matrix.properties],
                  [State('property-order', 'children')])
    def varname_click(*args):
        current_str = args[-1]

        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: triggered_id = None # nothing triggered the script (on multiapp load)

        current = current_str.split(" ") if current_str else list(Matrix.properties.keys())

        if triggered_id: # label_keyframe-period.n_clicks
            key = triggered_id.partition("_")[-1].rpartition(".")[0]
            if key in current: current.remove(key)
            current.append(key)

        try: current.remove("stats")
        except ValueError: pass

        return " ".join(current)

    @app.callback(
        Output('graph-hover-info', 'children'),
        [Input(graph_id, 'clickData') for graph_id in GRAPH_IDS],
        [State(graph_id, 'figure') for graph_id in GRAPH_IDS]
       +[State('list-params-'+key, "value") for key in Matrix.properties])
    def display_hover_data(*args):
        hoverData = args[:NB_GRAPHS]

        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)
        if triggered_id == ".": return

        pos = int(triggered_id.rpartition(".")[0].split("-")[1])
        data = hoverData[pos]

        figure = args[NB_GRAPHS:2*NB_GRAPHS][pos]
        variables = dict(zip(Matrix.properties.keys(), args[2*NB_GRAPHS:]))

        if not figure:
            return "Error, figure not found ..."

        click_info = types.SimpleNamespace()
        click_info.x = data['points'][0]['x']
        click_info.y = data['points'][0]['y']
        click_info.idx = data['points'][0]['curveNumber']
        click_info.legend = figure['data'][click_info.idx]['name']

        meta = figure['layout'].get('meta')
        if isinstance(meta, list): meta = meta[0]

        if not meta:
            return f"Error: no meta found for this graph ..."
        if 'name' not in meta:
            return f"Error: meta found for this graph has no name ..."

        obj = TableStats.stats_by_name[meta['name']]
        return obj.do_hover(meta.get('value'), variables, figure, data, click_info)

    @app.callback([Output("permalink", 'href'), Output("download", 'href')],
                  [Input('list-params-'+key, "value") for key in Matrix.properties]
                  +[Input('custom-config', 'value'),
                    Input('custom-config-saved', 'data'),
                    Input('property-order', 'children')])
    def get_permalink_cb(*args):
        try: triggered_id = dash.callback_context.triggered
        except IndexError: return dash.no_update, dash.no_update # nothing triggered the script (on multiapp load)

        search = get_permalink(args)

        return search, "/matrix/dl"+search

    for _graph_idx, _graph_id in enumerate(GRAPH_IDS):
        def create_callback(graph_idx, graph_id):
            @app.callback([Output(graph_id, 'style'),
                           Output(graph_id+"-txt", 'style')],
                          [Input('list-params-stats', "value")])
            def graph_style(stats_values):
                try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
                except IndexError: triggered_id = None # nothing triggered the script (on multiapp load)

                if not isinstance(stats_values, list):
                    # only 1 elt in stats_values dropdown, a str is returned instead of a list.
                    # That makes the following silly ...
                    stats_values = [stats_values]

                if (graph_idx != "graph-for-dl" and (graph_idx + 1) > len(stats_values)
                    or not triggered_id or not (stats_values and stats_values[0])):
                    return {"display": 'none'},  {"display": 'none'},

                graph_style = {}

                graph_style["display"] = "block"
                graph_style["height"] = f"{100/(min(NB_GRAPHS, len(stats_values))) if stats_values else 100:.2f}vh"
                text_style = {"display": "block"}

                table_stat = TableStats.stats_by_name[stats_values[graph_idx]]
                print("Show", table_stat.name)

                try:
                    if table_stat.no_graph: # may raise AttributeError
                        graph_style["display"] = 'none'
                except AttributeError: pass

                return graph_style, text_style

            @app.callback([Output(graph_id, 'figure'),
                           Output(graph_id+"-txt", 'children')],
                          [Input('list-params-'+key, "value") for key in Matrix.properties]
                          +[Input("lbl_params", "n_clicks")]
                          +[Input('property-order', 'children')]
                          +[Input('config-title', 'n_clicks'),
                            Input('custom-config', 'value'),
                            Input('custom-config-saved', 'data')],
                          [State('custom-config-saved', 'data-label')]
            )
            def graph_figure_cb(*args):
                return graph_figure(*args)

            def graph_figure(*_args):
                if dash.callback_context.triggered:
                    try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
                    except IndexError:
                        return dash.no_update, "" # nothing triggered the script (on multiapp load)
                    except dash.exceptions.MissingCallbackContextException: triggered_id = '<manually triggered>'
                else: triggered_id = '<manually triggered>'

                *args, cfg_n_clicks, config, config_saved, config_init = _args

                if triggered_id == "custom-config.value":
                    if not config or config.startswith("_"):
                        return dash.no_update, dash.no_update

                cfg = {}
                lst = (config_saved if config_saved else []) \
                    + ([config] if config else []) \
                    + (config_init if cfg_n_clicks is None else [])

                for cf in lst:
                    k, _, v = cf.partition("=")
                    if k.startswith("_"): continue
                    v = int(v) if v.isdigit() else v
                    cfg[k] = v

                order_str = args[-1]
                var_order = order_str.split(" ")+['stats'] if order_str \
                    else list(Matrix.properties.keys())

                params = dict(zip(Matrix.properties.keys(), args[:len(Matrix.properties)]))

                stats_values = params["stats"]
                if not stats_values:
                    return {}, ""

                if not isinstance(stats_values, list):
                    # only 1 elt in stats_values dropdown, a str is returned instead of a list.
                    # That makes the following silly ...
                    stats_values = [stats_values]

                if graph_idx != "graph-for-dl" and (not stats_values
                                                    or (graph_idx + 1) > len(stats_values)):
                    return dash.no_update, dash.no_update

                table_stat = TableStats.stats_by_name[stats_values[graph_idx]]

                variables = {k:(Matrix.properties[k]) for k, v in params.items() \
                             if k != "stats" and v == "---"}

                ordered_vars = sorted(variables.keys(), key=var_order.index)
                ordered_vars.reverse()

                param_lists = [[(key, v) for v in variables[key]] for key in ordered_vars]

                return table_stat.do_plot(ordered_vars, params, param_lists, variables, cfg)

            if graph_id == "graph-for-dl":
                TableStats.graph_figure = graph_figure

        # must use internal function to save 'table_stat' closure context
        create_callback(_graph_idx, _graph_id)
    create_callback(0, "graph-for-dl")
