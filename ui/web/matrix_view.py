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

import measurement.perf_viewer

class TableStats():
    all_stats = []

    interesting_tables = defaultdict(list)

    def __init__(self, id_name, name, table, field, units, min_rows=0):
        self.id_name = id_name
        self.name = name
        self.table = table
        self.field = field
        self.units = units
        self.min_rows = min_rows

        TableStats.interesting_tables[table].append(self)
        TableStats.all_stats.append(self)

    def process(self, table_def, rows):
        row_id = table_def.partition("|")[2].split(";").index(self.field)
        total = sum(row[row_id] for row in rows)

        return total/len(rows)

TableStats("client_cpu", "Client CPU (%)", "host.client-pid", "client-pid.cpu_user", "%")
TableStats("qemu_cpu", "Qemu CPU (%)", "host.server-pid", "server-pid.cpu_user", "%")
TableStats("host_gpu_video", "Host Video (%)", "host.gpu", "gpu.video", "%")
TableStats("host_gpu_render", "Host Render (%)", "host.gpu", "gpu.render", "%")
TableStats("guest_cpu", "Guest CPU (%)", "guest.guest-pid", "guest-pid.cpu_user", "%")
TableStats("frame_size", "Frame Size (B)", "host.host", "host.frame_size", "B", min_rows=10)

class Matrix():
    properties = defaultdict(set)
    entry_map = {}

    broken_files = []

FileEntry = types.SimpleNamespace

KEY_ORDER = "webpage", "record_time", "codec", "params"
params_order = None

def parse_data(filename):
    for line in open(filename).readlines():
        if not line.strip(): continue
        entry = FileEntry()

        # aqua 30s gst.vp8.vaapivp8enc framerate=10;gst.prop=target-bitrate=1000;gst.prop=rate-control=vbr;gst.prop=keyframe-period=0 | logs/matrix_aqua_30s_20190929-172656.rec
        entry.key, entry.filename = line.strip().replace("gst.prop=", "").split(" | ")
        entry.__dict__.update(dict(zip(KEY_ORDER, entry.key.split())))

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

        for param in entry.params.split(";"):
            key, value = param.split("=")
            try: value = int(value)
            except ValueError: pass # not a number, keep it as a string
            Matrix.properties[key].add(value)

        Matrix.entry_map[entry.key] = entry

        entry.stats = {}
        for table_def, (table_name, table_rows) in entry.tables.items():
            for table_stats in TableStats.interesting_tables[table_name]:

                entry.stats[table_stats.name] = table_stats.process(table_def, table_rows)

        for stat in TableStats.all_stats:
            Matrix.properties["stats"].add(stat.name)

    for key, values in Matrix.properties.items():
        print(f"{key:20s}: {', '.join(map(str, values))}")

def build_layout():
    controls = [html.B("Parameters:"), html.Br()]
    for key, values in Matrix.properties.items():
        options = [{'label': i, 'value': i} for i in sorted(values)]

        len_is_1 = len(values) == 1
        if not len_is_1:
            options.insert(0, {'label': "[ all ]", 'value': "---"})

        tag = dcc.Dropdown(
                id='list-params-'+key,
                options=options, disabled=len_is_1,
                value=options[0]['value'] if len_is_1 else "---",
            searchable=False, clearable=False
            )
        controls += [f"{key}: ", tag]

    invalids = [html.B("Invalids:"), html.Br(),
                html.Button("Show", id="invalids-show"),
                html.Button("Delete", id="invalids-delete")]

    graph_children = []
    for table_stat in TableStats.all_stats:
        graph_children += [dcc.Graph(id=table_stat.id_name, style={"display": "block"})]

    return html.Div([html.Div(children=controls+invalids, className='two columns'),
                     html.Div("nothing yet", id='text-box', className='four columns'),
                     html.Div(children=graph_children, id='graph-box', className='six columns')])

def process_selection(params):
    params = {k:(Matrix.properties[k] if v == "---" else [v]) for k, v in params.items() }

    param_lists = [[(key, v) for v in value] for key, value in params.items() if key != "stats"]

    total_expe = functools.reduce(operator.mul, map(len, param_lists), 1)

    if total_expe > 150:
        return f"Select more parameters ({total_expe} combinations with current selection)"

    children = []
    for entry_props in itertools.product(*param_lists):
        entry_dict = dict(entry_props)
        entry_dict["params"] = ";".join([f"{k}={entry_dict[k]}" for k in params_order])
        key = " ".join([entry_dict[k] for k in KEY_ORDER])

        try: entry = Matrix.entry_map[key]
        except KeyError: continue

        title = " ".join(f"{k}={v}" for k, v in entry_dict.items() if k not in ("params", "stats") and len(params[k]) > 1)
        if not title: title = "Single match"

        link = html.A("view", target="_blank", href="/viewer/"+entry.filename)

        entry_stats = [html.Li(f"{k}: {int(v)}") for k, v in entry.stats.items() if k in params["stats"]]
        entry_html = [title, " [", link, "]", html.Ul(entry_stats)]

        children.append(html.Li(entry_html))


    return [html.P(f"Nb expe selected: {len(children)} ({total_expe-len(children)} missing), DB total: {len(Matrix.entry_map)}"), html.Ul(children)]

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
            def graph_style(stats_value):
                try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
                except IndexError: return # nothing triggered the script (on multiapp load)
                style = {}
                if stats_value == "---":
                    style["display"] = "block"
                else:
                    style["display"] = "block" if stats_value == table_stat.name else "none"
                if style["display"] == "block":
                    print("Show",table_stat.name )
                return style

            @app.callback(Output(table_stat.id_name, 'figure'),
                          [Input('list-params-'+key, "value") for key in Matrix.properties])
            def graph_figure(*args):
                params = dict(zip([key for key in Matrix.properties], args))

                stats_value = params["stats"]
                if stats_value not in ("---", table_stat.name):
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
                    layout.yaxis = dict(title=table_stat.name)

                    x = []; y = []
                    for param, values in variables.items():
                        for value in sorted(values):
                            params[param] = value
                            params["params"] = ";".join([f"{k}={params[k]}" for k in params_order])
                            key = " ".join([params[k] for k in KEY_ORDER])

                            try: entry = Matrix.entry_map[key]
                            except KeyError: continue # missing experiment

                            x.append(f"{value}")
                            y.append(entry.stats[table_stat.name])

                    data.append({'x': x, 'y': y, 'type': 'bar', 'name': 'Cars'})
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
