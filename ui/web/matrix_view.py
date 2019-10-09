from collections import defaultdict
import os
import types
import itertools, functools, operator

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Output, Input, State
import plotly
import plotly.graph_objs as go

import datetime

import measurement.perf_viewer

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

    def process(self, table_def, rows):
        class FutureValue():
            def __init__(self):
                self.computed = False
                self._value = None
                self._stdev = None

            @property
            def value(myself):
                if myself._value is not None: return myself._value

                myself._value, myself._stdev = self.do_process(table_def, rows)
                return myself._value

            @property
            def stdev(myself):
                if myself._value is not None:
                    _not_used = myself.value # force trigger the computation

                return myself._stdev

            def __str__(myself):
                val = f"{myself.value:{self.fmt}}{self.unit}"
                if myself.stdev:
                    val += f" +/- {myself.stdev:{self.fmt}}{self.unit}"
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
        import statistics
        row_id = table_def.partition("|")[2].split(";").index(self.field)
        values = [row[row_id] for row in rows]

        return statistics.mean(values) / self.divisor, statistics.stdev(values) / self.divisor

TableStats.PerSeconds("frame_size", "Frame Bandwidth", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".0f", "KB/s", min_rows=10, divisor=1000)

for name in ("server", "client", "guest"):
    TableStats.Average(f"{name}_gpu_video", f"{name.capitalize()} GPU Video",
                       "server.gpu", "gpu.video", ".0f", "%")
    TableStats.Average(f"{name}_gpu_render", f"{name.capitalize()} GPU Render", "server.gpu",
                       "gpu.render", ".0f",  "%")

    TableStats.Average(f"{name}_cpu", f"{name.capitalize()} CPU", f"{name}.{name}-pid",
                       f"{name}-pid.cpu_user", ".0f", "%")

TableStats.Average(f"client_queue", f"Client Queue", "client.client", "client.queue", ".2f", "")

class Matrix():
    properties = defaultdict(set)
    entry_map = {}

    broken_files = []

FileEntry = types.SimpleNamespace

KEY_ORDER = "webpage", "record_time", "codec", "params", "resolution"
params_order = None

def parse_data(filename):
    if not os.path.exists(filename): return

    for line in open(filename).readlines():
        if not line.strip(): continue
        if line.startswith("#"): continue
        entry = FileEntry()

        # cubemap | 30s | gst.vp8.vaapivp8enc | framerate=10;target-bitrate=1000;rate-control=vbr;keyframe-period=0 | 1199x1919 | logs/matrix_30s_20191008-173112.rec
        entry.key, _, entry.filename = line.strip().replace("gst.prop=", "").rpartition(" | ")
        entry.__dict__.update(dict(zip(KEY_ORDER, entry.key.split(" | "))))

        global params_order
        if params_order is None:
            params_order = [e.partition('=')[0] for e in \
                            entry.params.split(";")]

        if entry.key in Matrix.entry_map:
            print(f"WARNING: duplicated key: {entry.key} ({entry.filename})")
            continue

        if not os.path.exists(entry.filename): continue

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

        Matrix.properties["codec"].add(entry.codec)
        Matrix.properties["record_time"].add(entry.record_time)
        Matrix.properties["webpage"].add(entry.webpage)
        Matrix.properties["resolution"].add(entry.resolution)

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

def build_layout():
    controls = [html.B("Parameters:"), html.Br()]
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
            attr["value"] = "---"

        tag = dcc.Dropdown(id='list-params-'+key, options=options,
                           **attr, searchable=False, clearable=False)

        controls += [f"{key}: ", tag]

    invalids = [html.B("Invalids:"), html.Br(),
                html.Button("Show", id="invalids-show"),
                html.Button("Delete", id="invalids-delete")]

    graph_children = []
    for table_stat in TableStats.all_stats:
        graph_children += [dcc.Graph(id=table_stat.id_name, style={"display": "none"})]

    return html.Div([html.Div(children=controls+invalids, className='two columns'),
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
    @app.callback(Output("text-box", 'children'),
                  [Input('list-params-'+key, "value") for key in Matrix.properties] +
                  [Input('invalids-show', 'n_clicks'),Input('invalids-delete', 'n_clicks')])
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
                return style

            @app.callback(Output(table_stat.id_name, 'figure'),
                          [Input('list-params-'+key, "value") for key in Matrix.properties])
            def graph_figure(*args):
                params = dict(zip([key for key in Matrix.properties], args))

                stats_values = params["stats"]
                if not stats_values or table_stat.name not in stats_values:
                    return dash.no_update

                variables = {k:(Matrix.properties[k]) for k, v in params.items() \
                             if k != "stats" and v == "---"}

                data = []
                layout = go.Layout()
                if len(variables) == 0:
                    layout.title = "Select at least 1 variable parameter..."
                elif len(variables) == 1:
                    var_name = list(variables.items())[0][0]
                    layout.title = table_stat.name + " vs " + var_name
                    layout.xaxis = dict(type='category', title=var_name)
                    layout.yaxis = dict(title=table_stat.name+ f"({table_stat.unit})")

                    x = []; y = []; y_err = []
                    for param, values in variables.items():
                        for value in sorted(values):
                            params[param] = value
                            params["params"] = ";".join([f"{k}={params[k]}" for k in params_order])
                            key = " | ".join([params[k] for k in KEY_ORDER])

                            try: entry = Matrix.entry_map[key]
                            except KeyError: continue # missing experiment

                            x.append(f"{value}")
                            y.append(entry.stats[table_stat.name].value)
                            y_err.append(entry.stats[table_stat.name].stdev)
                    if any(y_err):
                        y_error = dict(type='data', visible=True,
                                       array=y_err)
                    else: y_error = None

                    data.append({'x': x, 'y': y, 'type': 'bar', 'name': table_stat.name,
                                 'error_y' : y_error})
                else:
                    layout.title = f"Too many variable parameters ({', '.join(variables)}) ..."

                return { 'data': data, 'layout': layout}


        # must use internal function to save 'table_stat' closure context
        create_callback(_table_stat)


def main(filename):
    parse_data(filename)

    external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
    app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    app.layout = build_layout()
    build_callbacks(app)
    print("---")
    app.run_server(debug=True)

if __name__ == "__main__":
    exit(main())
