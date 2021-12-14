from collections import defaultdict
import datetime

import statistics

import plotly.graph_objs as go
import plotly.subplots
import dash_html_components as html
import dash_core_components as dcc

import common
from common import Matrix

def register_all():
    for stat in TableStats.all_stats:
        register = False
        if not isinstance(stat, TableStats): continue
        for entry in Matrix.processed_map.values():
            if entry.is_gathered:
                entry.stats[stat.name] = gathered_stats = []
                for gathered_entry in entry.results:
                    if not gathered_entry.results: continue
                    if stat.field not in gathered_entry.results.__dict__: continue

                    gathered_stats.append(stat.process(gathered_entry))
                if gathered_stats:
                    register = True
            else:
                d = entry.results if isinstance(entry.results, dict) else entry.results.__dict__
                if stat.field not in d: continue

                register = True

            entry.stats[stat.name] = stat.process(entry)

        if not register: continue

        Matrix.settings["stats"].add(stat.name)

class TableStats():
    all_stats = []
    stats_by_name = {}
    graph_figure = None

    @classmethod
    def _register_stat(clazz, stat_obj):
        print(stat_obj.name)

        clazz.all_stats.append(stat_obj)

        if stat_obj.name in clazz.stats_by_name:
            raise Exception(f"Duplicated name: {stat_obj.name}")

        clazz.stats_by_name[stat_obj.name] = stat_obj

    def __init__(self, id_name, name, field, fmt, unit, higher_better, divisor=1, **kwargs):
        self.id_name = id_name
        self.name = name
        self.field = field
        self.fmt = fmt
        self.unit = unit
        self.higher_better = higher_better
        self.divisor = divisor
        self.kwargs = kwargs

        self.do_process = None

        TableStats._register_stat(self)

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.id_name

    @classmethod
    def Custom(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        def process(entry):
            raise RuntimeError("Should not be called ...")
        obj.do_process = process
        return obj

    @classmethod
    def Value(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_value_dev
        return obj

    @classmethod
    def ValueDev(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_value_dev
        return obj

    @classmethod
    def MeanStd(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_mean_std
        return obj

    def process(self, entry):
        class FutureValue():
            def __init__(self):
                self.computed = False
                self._value = None
                self._stdev = None

            @property
            def value(myself):
                if myself._value is not None: return myself._value
                try:
                    v = self.do_process(entry)
                except Exception as e:
                    print(f"ERROR: Failed to process field '{self.field}' with"
                          f"{self.do_process.__self__.__class__.__name__}.{self.do_process.__name__}:")
                    print(e.__class__.__name__, e)
                    print()
                    return 0

                try: myself._value, *myself._stdev = v
                except TypeError: # cannot unpack non-iterable ... object
                    myself._value = v

                return myself._value

            @property
            def stdev(myself):
                if myself._value is not None:
                    _not_used = myself.value # force trigger the computation

                return myself._stdev

            def __str__(myself):
                if myself.value is None: return "N/A"

                val = f"{myself.value:{self.fmt}}{self.unit}"
                if not myself.stdev:
                    pass
                elif len(myself.stdev) == 1:
                    if myself.stdev[0] is not None:
                        val += f" +/- {myself.stdev[0]:{self.fmt}}{self.unit}"
                elif len(myself.stdev) == 2:
                    if myself.stdev[0] is not None:
                        val += f" + {myself.stdev[0]:{self.fmt}}"
                    if myself.stdev[1] is not None:
                        val += f" - {myself.stdev[1]:{self.fmt}}"
                    val += str(self.unit)
                return val

        return FutureValue()

    def process_gathered_value_dev(self, entry):
        values = [self.process_value_dev(gathered_entry)[0]
                  for gathered_entry in entry.results]
        values = [v for v in values if v is not None]

        mean = statistics.mean(values) / self.divisor

        stdev = statistics.stdev(values) if len(values) > 2 else 0

        return mean, (stdev / self.divisor)

    def process_value_dev(self, entry):
        if entry.is_gathered:
            return self.process_gathered_value_dev(entry)

        value = entry.results.__dict__[self.field]

        if value is None:
            return None, None

        if isinstance(value, list):
            print(f"WARNING: {entry.location}.results.{self.field} is "
                  f"a list of length {len(value)}")
            value = value[0]

        dev_field = self.kwargs.get('dev_field')

        dev_value = entry.results.__dict__[dev_field] if dev_field else 0

        return value, dev_value

    def process_mean_std(self, entry):
        values = entry.results.__dict__[self.field]

        if not isinstance(value, list):
            print(f"WARNING: {entry.location}.results.{self.field} is "
                  f"NOT a list of length ({values})")
            values = [values]

        if not values:
            print(f"WARNING: {entry.location}.results.{self.field} is "
                  f"an empty list")
            return 0, 0

        mean = statistics.mean(values) / self.divisor

        stdev = statistics.stdev(values) if len(values) > 2 else 0

        return mean, (stdev / self.divisor)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        ax = figure['data'][click_info.idx]['xaxis']

        xaxis = 'xaxis' + (ax[1:] if ax != 'x' else '')
        yaxis = figure['layout']['yaxis']['title']['text']

        try: xaxis_name = figure['layout'][xaxis]['title']['text']
        except KeyError: xaxis_name = ''

        props = ", ".join([click_info.x, click_info.legend, xaxis_name]).split(", ")
        value = f"{yaxis}: {click_info.y:.2f}"

        entry, msg = TableStats.props_to_hoverlink(variables, props, value)

        graph = self.entry_to_hovergraph(entry) \
            if entry else ""

        return [*msg, graph]

    def entry_to_hovergraph(self, entry):
        #
        # needs to be changed
        #
        if not hasattr(entry, "tables"):
            return ""

        for table_def, (table_name, table_rows) in entry.tables.items():
            if (table_name != self.table and
                not (self.table.startswith("?.") and table_name.endswith(self.table[1:]))):
                continue

            table_simple_name = table_name.split(".")[1]

            def get_values(field_name):
                row_id = table_def.partition("|")[2].split(";").index(field_name)
                return [row[row_id] for row in table_rows if row[row_id] is not None]

            try:
                x = get_values(f"{table_simple_name}.msg_ts")
            except ValueError:
                try:
                    x = get_values(f"time")
                except ValueError:
                    print(f"props_to_hovergraph: Cannot find {table_simple_name}.msg_ts or time field ...")
                    return ""

            field = self.field if not isinstance(self.field, tuple) else self.field[1]

            y = get_values(field)
            from . import graph
            try: x = graph.GraphFormat.as_timestamp(x, y)
            except ValueError: #  year 50265933 is out of range
                x = graph.GraphFormat.as_timestamp([_x/1000000 for _x in x], y)

            fig = go.Figure(data=go.Scatter(x=x, y=y))

            fig.update_layout(yaxis_title=f"{self.name} ({self.unit})")
            return dcc.Graph(figure=fig)

        return "Table not found ..."

    @staticmethod
    def props_to_hoverlink(variables, props, value):
        for prop in props:
            try: k, v = prop.split('=')
            except ValueError: continue # not enough values to unpack (expected 2, got 1)
            variables[k] = v

        entry = Matrix.get_record(variables)
        if not entry:
            return None, f"Error: record not found in matrix ..."

        loc = entry.location.replace(common.RESULTS_PATH+"/", "")
        msg = [f"{loc} ⇒ {value}"]

        return entry, msg


    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        from matrix_view import natural_keys
        from matrix_view import COLORS
        cfg_plot_mode = cfg.get('stats.var_length', "")

        if cfg_plot_mode:
            var_length = int(cfg_plot_mode)
            print(f"Using var_length={var_length} instead of {len(variables)}")
        else:
            var_length = len(variables)

        data = []
        layout = go.Layout()
        layout.hovermode = 'closest'
        layout.meta = dict(name=self.name),

        if len(variables) == 0:
            layout.title = "Select at least 1 variable parameter..."
            return [{'data': data, 'layout': layout}]

        *second_vars, legend_var = ordered_vars
        second_vars.reverse()

        layout.title = f"{self.name} vs " + " x ".join(ordered_vars[:-1]) + " | " + ordered_vars[-1]
        layout.yaxis = dict(title=self.name+ f" ({self.unit})")
        layout.plot_bgcolor='rgb(245,245,240)'
        subplots = {}

        if second_vars:
            subplots_var = second_vars[-1]

            showticks = len(second_vars) == 2

            for i, subplots_key in enumerate(sorted(variables[subplots_var], key=natural_keys)):
                subplots[subplots_key] = f"x{i+1}"
                ax = f"xaxis{i+1}"
                layout[ax] = dict(title=f"{subplots_var}={subplots_key}",
                                  type='category', showticklabels=showticks, tickangle=45)
        else:
            subplots_var = None
            subplots[subplots_var] = "x1"
            layout["xaxis1"] = dict(type='category', showticklabels=True, tickfont=dict(size=18))

        x = defaultdict(list); y = defaultdict(list); y_err = defaultdict(list)
        legend_keys = set()
        legend_names = set()
        legends_visible = []
        subplots_used = set()

        for entry in Matrix.all_records(params, param_lists):
            if self.name not in entry.stats:
                print(f"Stat '{self.name}' not found for entry '{entry.location}'")
                continue

            x_key = ", ".join([f'{v}={params[v]}' for v in reversed(second_vars) if v != subplots_var])
            legend_name = f"{legend_var}={params[legend_var]}"
            legend_key = (legend_name, params[subplots_var] if subplots_var else None)

            if var_length > 3 and x[legend_key]:
                prev_first_param = x[legend_key][-1].partition(" ")[0]
                first_param = x_key.partition(" ")[0]

                if prev_first_param != first_param:
                    x[legend_key].append(None)
                    y[legend_key].append(None)
                    y_err[legend_key].append(None)

            legend_keys.add(legend_key)
            if not x_key: x_key = legend_key[0].split("=")[1]

            legend_names.add(legend_name)
            x[legend_key].append(x_key)

            y[legend_key].append(entry.stats[self.name].value)
            y_err[legend_key].append(entry.stats[self.name].stdev)

        # ---
        def prepare_histogram(legend_key, color):
            plot_args['type'] = 'bar'
            plot_args['marker'] = dict(color=color)

        def plot_histogram_err(legend_key):
            error_y = plot_args['error_y'] = dict(type='data', visible=True)
            error_y['array'] = [err[0] for err in y_err[legend_key]]

            if len(y_err[legend_key][0]) == 2:
                error_y['arrayminus'] = [err[1] for err in y_err[legend_key]]

        # ---

        def prepare_scatter(legend_key, color):
            if var_length < 5:
                plot_args['type'] = 'line'
                plot_args['line'] = dict(color=color)
            else:
                plot_args['mode'] = 'markers'
                plot_args['marker'] = dict(color=color)

        def prepare_scatter_short_err(legend_key):
            y_err_above = [];  y_err_below = []
            for _y, _y_error in zip(y[legend_key], y_err[legend_key]):
                # above == below iff len(_y_error) == 1
                if None in (_y, _y_error): continue

                y_err_above.append(_y+_y_error[0])
                y_err_below.append(_y-_y_error[-1])

            y_err_data = y_err_above+list(reversed(y_err_below))
            x_err_data = x[legend_key]+list(reversed(x[legend_key]))

            return x_err_data, y_err_data

        def prepare_scatter_long_err(legend_key):
            y_err_data = []; x_err_data = []

            x_err_current = []; y_err_above = [];  y_err_below = []

            for _x, _y, _y_error in zip(x[legend_key] + [None],
                                        y[legend_key] + [None],
                                        y_err[legend_key] + [None]):

                if _x is not None:
                    if None not in (_y, _y_error):
                        # above == below iff len(_y_error) == 1
                        y_err_above.append(_y+_y_error[0])
                        y_err_below.append(_y-_y_error[-1])
                    else:
                        y_err_above.append(None)
                        y_err_below.append(None)
                    x_err_current.append(_x)
                    continue

                x_err_data += x_err_current \
                    + list(reversed(x_err_current)) \
                    + [x_err_current[0], None]

                y_err_data += y_err_above \
                    + list(reversed(y_err_below)) \
                    + [y_err_above[0], None]
                x_err_current = []; y_err_above = [];  y_err_below = []

            return x_err_data, y_err_data

        def plot_scatter_err(legend_key, err_data, y_max):
            x_err_data, y_err_data = err_data

            data.append(go.Scatter(
                x=x_err_data, y=y_err_data,
                legendgroup=legend_name + ("(stdev)" if var_length >= 4 else ""),
                showlegend=False, hoverinfo="skip",
                fill='toself', fillcolor='rgba(0,100,80,0.2)',
                line_color='rgba(0,0,0,0)', xaxis=ax,
                name=legend_name + (" (stdev)" if var_length >= 4 else "")
            ))

            return max([yval for yval in [y_max]+y_err_data if yval is not None])

        y_max = 0
        from matrix_view import natural_keys
        legend_keys = sorted(list(legend_keys), key=natural_keys)
        legend_names = sorted(list(legend_names), key=natural_keys)

        DO_LOCAL_SORT = True
        for legend_key in legend_keys:
            legend_name, subplots_key = legend_key
            ax = subplots[subplots_key]
            has_err = any(y_err[legend_key])

            color = COLORS(list(legend_names).index(legend_name))
            plot_args = dict()

            if var_length <= 2:
                prepare_histogram(legend_key, color)
            else:
                prepare_scatter(legend_key, color)

            if has_err and var_length < 5:
                if var_length <= 2:
                    err_data = plot_histogram_err(legend_key)
                else:
                    if var_length < 4:
                        err_data = prepare_scatter_short_err(legend_key)
                    else:
                        err_data = prepare_scatter_long_err(legend_key)

                    y_max = plot_scatter_err(legend_key, err_data, y_max)


            if var_length >= 5 and DO_LOCAL_SORT:
                # sort x according to y's value order
                x[legend_key] = [_x for _y, _x in sorted(zip(y[legend_key], x[legend_key]),
                                                             key=lambda v: (v[0] is None, v[0]))]
                # sort y by value (that may be None)
                y[legend_key].sort(key=lambda x: (x is None, x))
                if not layout.title.text.endswith(" (sorted)"):
                    layout.title.text += " (sorted)"

            # if 2 >= var_length > 5:
            #   need to sort and don't move the None location
            #   need to sort yerr as well

            showlegend = legend_name not in legends_visible
            if showlegend: legends_visible.append(legend_name)
            subplots_used.add(ax)

            y_max = max([yval for yval in [y_max]+y[legend_key] if yval is not None])

            data.append(dict(**plot_args, x=x[legend_key], y=y[legend_key],
                             legendgroup=legend_name,
                             xaxis=ax, name=legend_name,
                             showlegend=showlegend, hoverlabel= {'namelength' :-1}))

        do_sort = bool(cfg.get('stats.sort_bar', False))
        if do_sort and var_length <= 2:
            layout['xaxis'].categoryorder = 'trace'
            def get(_name):
                for trace in data:
                    if trace['name'] != _name: continue
                    return trace

            for _y, _x in sorted(zip(y.values(), x.keys())):
                name = _x[0]
                trace = get(name)
                data.remove(trace)
                data.append(trace)

        if var_length > 2:
            # force y_min = 0 | y_max = max visible value (cannot set only y_min)
            # if var_length <= 2:
            #   bar plot start from 0, y_max hard to compute with error bars
            layout.yaxis.range = [0, y_max]

        for i, ax in enumerate(sorted(subplots_used, key=lambda x: int(x[1:]))):
            axis = "xaxis"+ax[1:]
            layout[axis].domain = [i/len(subplots_used), (i+1)/len(subplots_used)]

        layout.legend.traceorder = 'normal'

        return { 'data': data, 'layout': layout}, [""]
