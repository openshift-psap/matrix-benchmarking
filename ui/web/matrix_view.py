from collections import defaultdict
import os
import types
import itertools, functools, operator

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Output, Input, State, ClientsideFunction
import plotly
import plotly.graph_objs as go
import plotly.subplots

import datetime
import statistics

import measurement.perf_viewer

COLORS = [
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

class TableStats():
    all_stats = []
    stats_by_name = {}

    interesting_tables = defaultdict(list)

    def __init__(self, id_name, name, table, field, fmt, unit, min_rows=0, divisor=1):
        self.id_name = id_name
        self.name = name
        self.table = table
        self.field = field
        self.unit = unit
        self.fmt = fmt
        self.min_rows = min_rows
        self.divisor = divisor

        self.do_process = None

        TableStats.interesting_tables[table].append(self)
        TableStats.all_stats.append(self)
        if self.name in TableStats.stats_by_name:
            raise Exception(f"Duplicated name: {self.name}")
        TableStats.stats_by_name[self.name] = self

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.id_name

    @classmethod
    def Average(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_average
        return obj

    @classmethod
    def PerSeconds(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_per_seconds
        return obj

    @classmethod
    def KeyFramesSize(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_keylowframes_size(keyframes=True)
        return obj

    @classmethod
    def LowFramesSize(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)

        obj.do_process = obj.process_keylowframes_size(lowframes=True)
        return obj

    @classmethod
    def KeyLowFramesSize(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_keylowframes_size(lowframes=True, keyframes=True)
        return obj

    def process(self, table_def, rows):
        class FutureValue():
            def __init__(self):
                self.computed = False
                self._value = None
                self._stdev = None

            @property
            def value(myself):
                if myself._value is not None: return myself._value

                myself._value, *myself._stdev = self.do_process(table_def, rows)
                return myself._value

            @property
            def stdev(myself):
                if myself._value is not None:
                    _not_used = myself.value # force trigger the computation

                return myself._stdev

            def __str__(myself):
                val = f"{myself.value:{self.fmt}}{self.unit}"
                if len(myself.stdev) == 1:
                    val += f" +/- {myself.stdev[0]:{self.fmt}}{self.unit}"
                elif len(myself.stdev) == 2:
                    if myself.stdev[0]:
                        val += f" + {myself.stdev[0]:{self.fmt}}"
                    if myself.stdev[1]:
                        val += f" - {myself.stdev[1]:{self.fmt}}"
                    val += str(self.unit)
                return val

        return FutureValue()

    def process_per_seconds(self, table_def, rows):
        time_field, value_field = self.field

        indexes = table_def.partition("|")[2].split(";")

        time_row_id = indexes.index(time_field)
        value_row_id = indexes.index(value_field)

        values_total = sum(row[value_row_id] for row in rows)
        start_time = datetime.datetime.fromtimestamp(rows[0][time_row_id]/1000000)
        end_time = datetime.datetime.fromtimestamp(rows[-1][time_row_id]/1000000)

        return (values_total / (end_time - start_time).seconds) / self.divisor, 0

    def process_average(self, table_def, rows):
        row_id = table_def.partition("|")[2].split(";").index(self.field)
        values = [row[row_id] for row in rows]

        return statistics.mean(values) / self.divisor, statistics.stdev(values) / self.divisor

    def process_keylowframes_size(self, keyframes=False, lowframes=False):
        if not (keyframes or lowframes):
            raise ValueError("Must have keyframes or lowframes.") # impossible to reach

        def do_process(table_def, rows):
            time_field, value_field = self.field

            indexes = table_def.partition("|")[2].split(";")

            time_row_id = indexes.index(time_field)
            value_row_id = indexes.index(value_field)

            values = [row[value_row_id] for row in rows]
            mini, maxi = min(values), max(values)
            split = (mini+maxi)/2
            high_values = [v for v in values if v >= split]
            low_values = [v for v in values if v < split]

            if keyframes and lowframes:
                return (statistics.mean(low_values) / self.divisor,
                        statistics.mean(high_values) / self.divisor, 0)

            if keyframes:
                values = high_values
            elif lowframes:
                values = low_values
            else:
                assert False, "impossible to reach"

            return statistics.mean(values) / self.divisor, statistics.stdev(values) / self.divisor

        return do_process

TableStats.KeyFramesSize("keyframe_size", "Frame Size: keyframes", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".0f", "KB/s", divisor=1000)
TableStats.LowFramesSize("lowframe_size", "Frame Size: lowframes", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".0f", "KB/s", divisor=1000)
TableStats.KeyLowFramesSize("keylowframe_size", "Frame Size: keys+lows", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".0f", "KB/s", divisor=1000)

TableStats.PerSeconds("frame_size", "Frame Bandwidth", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".0f", "KB/s", min_rows=10, divisor=1000)

for name in ("server", "client", "guest"):
    TableStats.Average(f"{name}_gpu_video", f"{name.capitalize()} GPU Video",
                       f"{name}.gpu", "gpu.video", ".0f", "%")
    TableStats.Average(f"{name}_gpu_render", f"{name.capitalize()} GPU Render",
                       f"{name}.gpu", "gpu.render", ".0f",  "%")

    TableStats.Average(f"{name}_cpu", f"{name.capitalize()} CPU", f"{name}.{name}-pid",
                       f"{name}-pid.cpu_user", ".0f", "%")

TableStats.Average(f"client_queue", f"Client Queue", "client.client", "client.queue", ".2f", "")

class Matrix():
    properties = defaultdict(set)
    entry_map = {}

    broken_files = []

FileEntry = types.SimpleNamespace

KEY_ORDER = "webpage", "record_time", "codec", "params", "resolution", "experiment"
params_order = None

def parse_data(filename, reloading=False):
    if not os.path.exists(filename): return
    directory = filename.rpartition(os.sep)[0]
    expe_name = filename.split(os.sep)[1] # eg, filename = 'results/current/matrix.csv'

    for line in open(filename).readlines():
        if not line.strip(): continue
        if line.startswith("#"): continue
        entry = FileEntry()

        # cubemap | 30s | gst.vp8.vaapivp8enc | framerate=10;target-bitrate=1000;rate-control=vbr;keyframe-period=0 | 1199x1919 | logs/matrix_30s_20191008-173112.rec
        entry.key, _, entry.filename = line.strip().replace("gst.prop=", "").rpartition(" | ")
        entry.__dict__.update(dict(zip(KEY_ORDER, entry.key.split(" | "))))

        entry.key += f" | {expe_name}"

        global params_order
        if params_order is None:
            params_order = [e.partition('=')[0] for e in \
                            entry.params.split(";")]

        if entry.key in Matrix.entry_map:
            if not reloading:
                print(f"WARNING: duplicated key: {entry.key} ({entry.filename})")
            continue

        filepath = os.sep.join([directory, entry.filename])
        if not os.path.exists(filepath): continue
        entry.filename = filepath

        parser = measurement.perf_viewer.parse_rec_file(open(entry.filename))
        _, quality_rows = next(parser)

        entry.tables = {}

        while True:
            _, table_def = next(parser)
            if not table_def: break

            _, table_rows= next(parser)
            _, quality_rows = next(parser)

            table_name = table_def.partition("|")[0][1:]

            if not TableStats.interesting_tables[table_name]:
                continue # table not interesting

            keep = True
            for table_stat in TableStats.interesting_tables[table_name]:
                if table_stat.min_rows and len(table_rows) < table_stat.min_rows:
                    keep = False
                    msg = f"{table_name} has only {len(table_rows)} rows (min: {table_stat.min_rows})"
                    Matrix.broken_files.append((entry.filename, msg))
                    break

            if not keep: break # not enough rows, skip the record
            entry.tables[table_def] = table_name, table_rows

        if table_def is not None: # didn't break because not enough entries
            continue

        Matrix.properties["experiment"].add(expe_name)
        Matrix.properties["resolution"].add(entry.resolution)
        Matrix.properties["codec"].add(entry.codec)
        Matrix.properties["record_time"].add(entry.record_time)
        Matrix.properties["webpage"].add(entry.webpage)

        for param in entry.params.split(";"):
            key, value = param.split("=")
            try: value = int(value)
            except ValueError: pass # not a number, keep it as a string
            Matrix.properties[key].add(value)

        Matrix.entry_map[entry.key] = entry

        entry.stats = {}
        for table_def, (table_name, table_rows) in entry.tables.items():
            for table_stat in TableStats.interesting_tables[table_name]:
                entry.stats[table_stat.name] = table_stat.process(table_def, table_rows)

        for table_stat in TableStats.all_stats:
            Matrix.properties["stats"].add(table_stat.name)

    for key, values in Matrix.properties.items():
        print(f"{key:20s}: {', '.join(map(str, values))}")

def build_layout(app):
    matrix_controls = [html.B("Parameters:"), html.Br()]
    for key, values in Matrix.properties.items():
        options = [{'label': i, 'value': i} for i in sorted(values)]

        attr = {}
        if key == "stats":
            attr["multi"] = True

        elif len(values) == 1:
            attr["disabled"] = True
            attr["value"] = options[0]['value']
        else:
            options.insert(0, {'label': "[ all ]", 'value': "---"})

            if key == "experiment" and "current" in values:
                attr["value"] = "current"
            else:
                attr["value"] = "---"

        tag = dcc.Dropdown(id='list-params-'+key, options=options,
                           **attr, searchable=False, clearable=False)

        matrix_controls += [html.Span(f"{key}: ", id=f"label_{key}"), tag]

    invalids = [html.B("Invalids:"), html.Br(),
                html.Button("Show", id="invalids-show"),
                html.Button("Delete", id="invalids-delete")]

    aspect = [html.Br(), html.B("Aspect:"), html.Br(),
              dcc.Checklist(id="matrix-show-text", value='txt',
                            options=[{'label': 'Show text', 'value': 'txt'}]),
              html.Div(id='property-order')
    ]

    control_children = matrix_controls + aspect + invalids

    graph_children = []
    for table_stat in TableStats.all_stats:
        graph_children += [dcc.Graph(id=table_stat.id_name, style={"display": "none"})]


    graph_children += [html.Div(id="text-box:clientside-output")]

    return html.Div([html.Div(children=control_children, className='two columns'),
                     html.Div("nothing yet", id='text-box', className='four columns'),
                     html.Div(children=graph_children, id='graph-box', className='six columns')])

def process_selection(params):
    variables = [k for k, v in params.items() if v == "---"]

    params = {k:(Matrix.properties[k] if v == "---" else [v]) for k, v in params.items() }
    params["stats"] = params["stats"][0] # stats param is already a list
    if params["stats"] is None: params["stats"] = []

    param_lists = [[(key, v) for v in value] for key, value in params.items() if key != "stats"]

    total_expe = functools.reduce(operator.mul, map(len, param_lists), 1)

    if total_expe > 150:
        return f"Select more parameters ({total_expe} combinations with current selection)"

    children = []
    for entry_props in sorted(itertools.product(*param_lists)):
        entry_dict = dict(entry_props)
        entry_dict["params"] = ";".join([f"{k}={entry_dict[k]}" for k in params_order])
        key = " | ".join([entry_dict[k] for k in KEY_ORDER])

        try: entry = Matrix.entry_map[key]
        except KeyError: continue

        title = " ".join(f"{k}={v}" for k, v in entry_dict.items() if k not in ("params", "stats") and len(params[k]) > 1)
        if not title: title = "Single match"

        link = html.A("view", target="_blank", href="/viewer/"+entry.filename)

        entry_stats = []
        for stat_name, stat_value in entry.stats.items():
            if stat_name not in params["stats"]: continue
            table_stat = TableStats.stats_by_name[stat_name]

            entry_stats.append(html.Li(f"{stat_name}: {stat_value}"))

        entry_html = [title, " [", link, "]", html.Ul(entry_stats)]

        children.append(html.Li(entry_html))

    return [html.P(f"Showing {len(children)} experiments out of {len(Matrix.entry_map)} ({total_expe-len(children)} missing)"),
            html.P([html.B("Variables: "), ', '.join(variables)]),
            html.Ul(children)]

def build_callbacks(app):
    if not Matrix.properties:
        print("WARNING: Matrix empty, cannot build its GUI")
        return

    app.clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="resize_graph"),
        Output("text-box:clientside-output", "children"),
        [Input('text-box', "style"), Input('graph-box', "style")],
    )
    @app.callback([Output("text-box", 'style'), Output("graph-box", 'className'),],
                  [Input('matrix-show-text', "value")])
    def show_text(arg):
        if 'txt' in arg:
            return {}, 'six columns'
        else:
            return dict(display='none'), 'ten columns'

    @app.callback(Output("text-box", 'children'),
                  [Input('list-params-'+key, "value") for key in Matrix.properties] +
                  [Input('invalids-show', 'n_clicks'), Input('invalids-delete', 'n_clicks')])
    def param_changed(*args):
        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

        if triggered_id.startswith("list-params-"):
            return process_selection(dict(zip(Matrix.properties, args)))

        if triggered_id.startswith("invalids-show"):
            return ([html.P(html.B(f"Found {len(Matrix.broken_files)} invalid record files:"))]
                    +[html.P(f"{fname} | {msg}") for fname, msg in Matrix.broken_files])

        if triggered_id.startswith("invalids-delete"):
            ret = []
            for fname, msg in Matrix.broken_files:
                try:
                    os.unlink(fname)
                    ret += [html.P(f"{fname}: Deleted")]
                except Exception as e:
                    ret += [html.P(html.B(f"{fname}: Failed: {e}"))]
            Matrix.broken_files[:] = []
            return ret + [html.P(html.B("Local matrix state cleaned up."))]

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
            current.remove(key)
            current.append(key)

        try: current.remove("stats")
        except ValueError: pass

        return " ".join(current)

    for _table_stat in TableStats.all_stats:
        def create_callback(table_stat):
            @app.callback(Output(table_stat.id_name, 'style'),
                          [Input('list-params-stats', "value")])
            def graph_style(stats_values):
                try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
                except IndexError: triggered_id = None # nothing triggered the script (on multiapp load)

                style = {}
                style["display"] = "block" if triggered_id and table_stat.name in stats_values else "none"
                if style["display"] == "block":
                    print("Show",table_stat.name )
                style["height"] = f"{100/len(stats_values) if stats_values else 100:.2f}vh"

                return style

            @app.callback(Output(table_stat.id_name, 'figure'),
                          [Input('list-params-'+key, "value") for key in Matrix.properties]
                          +[Input('property-order', 'children')])
            def graph_figure(*args):
                order_str = args[-1]
                var_order = order_str.split(" ")+['stats'] if order_str \
                    else list(Matrix.properties.keys())

                params = dict(zip(Matrix.properties.keys(), args[:-1]))

                stats_values = params["stats"]
                if not stats_values or table_stat.name not in stats_values:
                    return dash.no_update

                variables = {k:(Matrix.properties[k]) for k, v in params.items() \
                             if k != "stats" and v == "---"}

                data = [[[], []]]
                layout = go.Layout()
                if len(variables) == 0:
                    layout.title = "Select at least 1 variable parameter..."

                elif len(variables) <= 4:
                    ordered_vars = sorted(variables.keys(), key=var_order.index)
                    ordered_vars.reverse()

                    param_lists = [[(key, v) for v in variables[key]] for key in ordered_vars]

                    *second_vars, legend_var = ordered_vars
                    second_vars.reverse()

                    layout.title = f"{table_stat.name} vs " + " x ".join(ordered_vars[:-1]) + " | " + ordered_vars[-1]
                    layout.yaxis = dict(title=table_stat.name+ f" ({table_stat.unit})")

                    subplots = {}
                    if second_vars:
                        subplots_var = second_vars[-1]
                        subplots_len = len(variables[subplots_var])

                        showticks = len(second_vars) == 2
                        for i, subplots_key in enumerate(sorted(variables[subplots_var])):
                            subplots[subplots_key] = f"x{i+1}"
                            ax = f"xaxis{i+1}"
                            layout[ax] = dict(title=f"{subplots_var}={subplots_key}",
                                              domain=[i/subplots_len, (i+1)/subplots_len],
                                              type='category', showticklabels=showticks, tickangle=45)
                    else:
                        subplots_var = None
                        subplots[subplots_var] = "x1"
                        layout["xaxis1"] = dict(type='category', showticklabels=False)

                    x = defaultdict(list); y = defaultdict(list); y_err = defaultdict(list)
                    legend_keys = set()
                    legend_names = set()
                    for param_values in sorted(itertools.product(*param_lists)):
                        params.update(dict(param_values))

                        params["params"] = ";".join([f"{k}={params[k]}" for k in params_order])

                        key = " | ".join([params[k] for k in KEY_ORDER])

                        try: entry = Matrix.entry_map[key]
                        except KeyError: continue # missing experiment

                        if table_stat.name not in entry.stats:
                            print(f"{table_stat.name} for entry '{key}'")
                            continue

                        x_key = " ".join([f'{v}={params[v]}' for v in reversed(second_vars) if v != subplots_var])
                        legend_name = f"{legend_var}={params[legend_var]}"
                        legend_key = (legend_name, params[subplots_var] if subplots_var else None)

                        if len(variables) > 3 and x[legend_key]:
                            prev_first_param = x[legend_key][-1].partition(" ")[0]
                            first_param = x_key.partition(" ")[0]

                            if prev_first_param != first_param:
                                x[legend_key].append(None)
                                y[legend_key].append(None)
                                y_err[legend_key].append(None)

                        legend_keys.add(legend_key)

                        legend_names.add(legend_name)
                        x[legend_key].append(x_key)
                        y[legend_key].append(entry.stats[table_stat.name].value)
                        y_err[legend_key].append(entry.stats[table_stat.name].stdev)

                    for legend_key in sorted(legend_keys):
                        legend_name, subplots_key = legend_key
                        ax = subplots[subplots_key]
                        has_err = any(y_err[legend_key])

                        color = COLORS[list(legend_names).index(legend_name)]
                        plot_args = dict()

                        if len(variables) <= 2:
                            plot_args['type'] = 'bar'
                            plot_args['marker'] = dict(color=color)
                            if has_err:
                                error_y = plot_args['error_y'] = dict(type='data', visible=True)
                                error_y['array'] = [err[0] for err in y_err[legend_key]]

                                if len(y_err[legend_key][0]) == 2:
                                    error_y['arrayminus'] = [err[1] for err in y_err[legend_key]]
                        else:
                            plot_args['type'] = 'line'
                            plot_args['line'] = dict(color=color)


                            if has_err:
                                if len(variables) < 4:
                                    y_err_above = [];  y_err_below = []
                                    for _y, _y_error in zip(y[legend_key], y_err[legend_key]):
                                        # above == below iff len(_y_error) == 1
                                        y_err_above.append(_y+_y_error[0])
                                        y_err_below.append(_y-_y_error[-1])

                                    y_err_data = y_err_above+list(reversed(y_err_below))
                                    x_err_data = x[legend_key]+list(reversed(x[legend_key]))
                                else:
                                    y_err_data = []; x_err_data = []

                                    x_err_current = []; y_err_above = [];  y_err_below = []

                                    for _x, _y, _y_error in zip(x[legend_key] + [None],
                                                                y[legend_key] + [None],
                                                                y_err[legend_key] + [None]):
                                        if _x is not None:
                                            # above == below iff len(_y_error) == 1
                                            y_err_above.append(_y+_y_error[0])
                                            y_err_below.append(_y-_y_error[-1])
                                            x_err_current.append(_x)
                                            continue
                                        #import pdb;pdb.set_trace()
                                        x_err_data += x_err_current \
                                            + list(reversed(x_err_current)) \
                                            + [x_err_current[0], None]

                                        y_err_data += y_err_above \
                                            + list(reversed(y_err_below)) \
                                            + [y_err_above[0], None]
                                        x_err_current = []; y_err_above = [];  y_err_below = []

                                data.append(go.Scatter(
                                    x=x_err_data, y=y_err_data,
                                    legendgroup=legend_name + "(stdev)" if len(variables) >= 4 else "",
                                    showlegend=(ax == "x1" and len(variables) >= 4), hoverinfo="skip",
                                    fill='toself', fillcolor='rgba(0,100,80,0.2)',
                                    line_color='rgba(0,0,0,0)',
                                    name=legend_name + " (stdev)", xaxis=ax
                                ))

                        data.append(dict(**plot_args, x=x[legend_key], y=y[legend_key],
                                         legendgroup=legend_name,
                                         xaxis=ax, name=legend_name,
                                         showlegend=(ax == "x1")))

                    layout.legend.traceorder = 'normal'
                else:
                    layout.title = f"Too many variable parameters ({', '.join(variables)}) ..."

                return { 'data': data, 'layout': layout}


        # must use internal function to save 'table_stat' closure context
        create_callback(_table_stat)


def main(filename):
    parse_data(filename)

    external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
    app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    app.layout = build_layout(app)
    build_callbacks(app)
    print("---")
    app.run_server(debug=True)

if __name__ == "__main__":
    exit(main("results/current/matrix.csv"))
