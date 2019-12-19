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

import urllib.parse
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

class Regression():
    def __init__(self, id_name, key_var, name, x_key, y_key):
        self.name = "Reg: " + name
        self.id_name = id_name
        self.x_key = x_key
        self.y_key = y_key
        self.key_var = key_var

        TableStats._register_stat(self)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return [html.P(f) for f in meta_value]

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()

        x = defaultdict(list)
        y = defaultdict(list)

        reg_x, reg_y = defaultdict(list), defaultdict(list)

        other_vars = ordered_vars[:]
        try: other_vars.remove(self.key_var)
        except ValueError:
            return { 'data': [], 'layout': dict(title="ERROR: Framerate parameter must be variable ...")}

        for param_values in sorted(itertools.product(*param_lists)):
            params.update(dict(param_values))

            key = "_".join([f"{k}={params[k]}" for k in key_order])

            try: entry = Matrix.entry_map[key]
            except KeyError:
                print(f"{key} missing")
                continue # missing experiment

            try:
                _x = entry.stats[self.x_key].value
                _y = entry.stats[self.y_key].value
            except KeyError:
                print(f"{self.x_key} or {self.y_key} missing values for ", key)
                continue

            legend_key = f"{self.key_var}={params[self.key_var]}"
            x[legend_key].append(_x)
            y[legend_key].append(_y)

            reg_key = "all" if not other_vars else \
                 " | ".join(f"{k}={params[k]}" for k in other_vars)
            reg_x[reg_key].append(_x)
            reg_y[reg_key].append(_y)

        for i, legend_key in enumerate(x.keys()):
            fig.add_trace(go.Scatter(x=x[legend_key], y=y[legend_key], mode='markers', name=legend_key,
                                     hoverlabel= {'namelength' :-1}, legendgroup=self.key_var,
                                     marker=dict(symbol="cross", size=15, color=COLORS[i])))

        fig.update_layout(yaxis=dict(zeroline=True, showgrid=False, rangemode='tozero',
                                     title=self.y_key),
                          xaxis=dict(title=self.x_key))

        import scipy
        import scipy.stats
        import numpy as np

        x_range = None
        formulae = []
        for i, reg_key in enumerate(reg_x.keys()):
            all_x = reg_x[reg_key]
            all_y = reg_y[reg_key]

            # https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.linregress.html
            slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(all_x, all_y)

            line = slope*np.array(all_x)+intercept
            fig.add_trace(go.Scatter(x=all_x, y=line, mode='lines', text="toto", hovertext="text",
                                     name=reg_key, line=dict(color=COLORS[i])))

            if not x_range: x_range = [all_x[0], all_x[-1]]
            x_range = [min(x_range[0], min(all_x)), max(x_range[1], max(all_x))]

            # need to change here: if slope/intercept too low, they appear as 0.00 !
            formulae.append(f"{reg_key} |" +
                            f"{self.y_key} = {slope:.2f} * {self.x_key} + {intercept:.2f} " +
                            f"| r={r_value:.3f}, p={p_value:.3f}, stdev={std_err:.3f} ")

        text_x_pos = x_range[0] + (x_range[1]-x_range[0])/2
        text = '<br>'.join(formulae)

        fig.update_layout(
            meta=dict(name=self.name, value=formulae),
        )

        fig.update_layout(title=f"{self.y_key} vs {self.x_key} | {' x '.join(other_vars)}")

        return fig

class HeatmapPlot():
    def __init__(self, name, table, title, x, y):
        self.name = "Heat: "+name
        self.id_name = name
        TableStats._register_stat(self)
        self.table = table
        self.title = title
        self.x = x
        self.y = y

    def do_hover(self, meta_value, variables, figure, data, click_info):
        name = figure['data'][click_info.idx]['name']

        if name == 'heatmap':
            z = data['points'][0]['z']
            return (f"Cannot get link to viewer for Heatmap layer. "
                    f"Try to hide it with double clicks ... "
                    f"[x: {click_info.x}, y: {click_info.y}, z: {z:.0f}%]")

        props = name.split(", ") if name else []

        value = f"[x: {click_info.x}, y: {click_info.y}]"

        return TableStats.props_to_hoverlink(variables, props, value)

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        table_def = None
        fig = go.Figure()
        all_x = []
        all_y = []

        if len(variables) > 4:
            return {'layout': {'title': f"Too many variables selected ({len(variables)} > 4)"}}

        for i, param_values in enumerate(sorted(itertools.product(*param_lists))):
            params.update(dict(param_values))

            key = "_".join([f"{k}={params[k]}" for k in key_order])

            try: entry = Matrix.entry_map[key]
            except KeyError: continue # missing experiment

            if table_def is None:
                for table_key in entry.tables:
                    if not table_key.startswith(f"#{self.table}|"): continue
                    table_def = table_key
                    break
                else:
                    return {'layout': {'title': f"Error: no table named '{table_key}'"}}

            table_fields = table_def.partition("|")[-1].split(";")
            try:
                x_row_id = table_fields.index(self.x[0])
                y_row_id = table_fields.index(self.y[0])
            except ValueError:
                return {'layout': {'title': f"Error: Could not find {self.x}/{self.y} in '{table_def}'"}}
            table_rows = entry.tables[table_def]
            x = [row[x_row_id] * self.x[2] for row in table_rows[1]]
            y = [row[y_row_id] * self.y[2] for row in table_rows[1]]

            if 'heat.min_x' in cfg or 'heat.max_x' in cfg:
                min_x = cfg.get('heat.min_x', min(x))
                max_x = cfg.get('heat.max_x', max(x))

                new_x = []
                new_y = []
                for _x, _y in zip(x, y):
                    if not (min_x <= _x <= max_x): continue
                    new_x.append(_x)
                    new_y.append(_y)
                x = new_x
                y = new_y

            name =  ", ".join(f"{k}={params[k]}" for k in variables)
            if not name: name = "single selection"
            all_x += x
            all_y += y

            if len(variables) < 3:
                fig.add_trace(go.Scatter(
                    xaxis = 'x', yaxis = 'y', mode = 'markers',
                    marker = dict(color = COLORS[i % len(COLORS)], size = 3 ),
                    name=name, legendgroup=name,
                    x = x, y = y,
                    hoverlabel= {'namelength' :-1}
                ))

            fig.add_trace(go.Histogram(
                xaxis = 'x2', marker = dict(color=COLORS[i % len(COLORS)]), showlegend=False, opacity=0.75,
                histnorm='percent',
                y = y, legendgroup=name, name=name,
                hoverlabel= {'namelength' :-1},
            ))
            fig.add_trace(go.Histogram(
                yaxis = 'y2', marker = dict(color=COLORS[i % len(COLORS)]), showlegend=False, opacity=0.75,
                x = x, legendgroup=name, name=name,
                histnorm='percent',
                hoverlabel= {'namelength' :-1}
            ))

        fig.add_trace(go.Histogram2d(
            xaxis='x', yaxis='y',
            x=all_x, y=all_y, name='heatmap', histnorm='percent',
            showscale=False,
            colorscale=[[0, '#e5ecf6'], # carefully chosen with gimp to match the plot background color
                        [0.1, '#e5ecf6'], # more or less hide the first 10%
                        [0.5, 'rgb(242,211,56)'], [0.75, 'rgb(242,143,56)'], [1, 'rgb(217,30,30)']]
        ))

        fig.update_layout(
            meta=dict(name=self.name),
            barmode='overlay',
            xaxis=dict(
                zeroline=True, showgrid=False, rangemode='tozero',
                domain=[0,0.85],
                title=self.x[1],
            ),
            yaxis=dict(
                zeroline=True, showgrid =False, rangemode='tozero',
                domain=[0,0.85],
                title=self.y[1],
            ),
            xaxis2=dict(
                zeroline=True, showgrid=False,
                domain=[0.85,1],
                title='% of frames',
            ),
            yaxis2=dict(
                zeroline=True, showgrid=False,
                domain=[0.85,1],
                title='% of frames',
            ),
            bargap=0, hovermode='closest',
            showlegend=True, title=self.title + " (in %)",
        )
        return fig


class TableStats():
    all_stats = []
    stats_by_name = {}

    interesting_tables = defaultdict(list)

    @classmethod
    def _register_stat(clazz, stat_obj):
        clazz.all_stats.append(stat_obj)

        if stat_obj.name in clazz.stats_by_name:
            raise Exception(f"Duplicated name: {stat_obj.name}")

        clazz.stats_by_name[stat_obj.name] = stat_obj

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

        TableStats._register_stat(self)
        TableStats.interesting_tables[table].append(self)

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
    def StartStopDiff(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_start_stop_diff
        return obj

    @classmethod
    def AgentActualFramerate(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_agent_framerate
        return obj

    @classmethod
    def ActualFramerate(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_actual_framerate
        return obj

    @classmethod
    def PerSecond(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_per_second
        return obj

    @classmethod
    def PerFrame(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_per_frame
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

    @classmethod
    def KeyFramePeriod(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_keyframe_period
        return obj

    @classmethod
    def AvgTimeDelta(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_average_time_delta
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

                v = self.do_process(table_def, rows)
                try:
                    myself._value, *myself._stdev = v
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

    def process_per_second(self, table_def, rows):
        if not rows: return None, None

        time_field, value_field = self.field

        indexes = table_def.partition("|")[2].split(";")

        time_row_id = indexes.index(time_field)
        value_row_id = indexes.index(value_field)

        values_total = sum(row[value_row_id] for row in rows)

        start_time = datetime.datetime.fromtimestamp(rows[0][time_row_id]/1000000)
        end_time = datetime.datetime.fromtimestamp(rows[-1][time_row_id]/1000000)

        return (values_total / (end_time - start_time).total_seconds()) / self.divisor, 0

    def process_per_frame(self, table_def, rows):
        time_field, value_field = self.field

        indexes = table_def.partition("|")[2].split(";")

        time_row_id = indexes.index(time_field)
        value_row_id = indexes.index(value_field)

        values_total = sum(row[value_row_id] for row in rows)

        nb_frames = len(rows)

        return (values_total / nb_frames) / self.divisor, 0

    def process_average(self, table_def, rows):
        row_id = table_def.partition("|")[2].split(";").index(self.field)
        values = [row[row_id] for row in rows]

        if not values: return None, None, None
        return statistics.mean(values) / self.divisor, statistics.stdev(values) / self.divisor

    def process_start_stop_diff(self, table_def, rows):
        if not rows: return 0

        row_id = table_def.partition("|")[2].split(";").index(self.field)

        return rows[-1][row_id] - rows[0][row_id]

    def process_agent_framerate(self, table_def, rows):
        quality_row_id = table_def.partition("|")[2].split(";").index(self.field)
        target_row_id = table_def.partition("|")[2].split(";").index(self.field.replace("_quality", "_requested"))

        actual_values = [row[quality_row_id] for row in rows if row[quality_row_id] is not None]
        target_values = [row[target_row_id] for row in rows if row[target_row_id] is not None]

        actual_mean = statistics.mean(actual_values) / self.divisor
        target_mean = statistics.mean(target_values) / self.divisor

        return actual_mean, (target_mean - actual_mean), 0

    def process_average_time_delta(self, table_def, rows):
        row_id = table_def.partition("|")[2].split(";").index(self.field)
        values = [row[row_id] for row in rows]

        ts = datetime.datetime.fromtimestamp
        delta = [(ts(stop/1000000) - ts(start/1000000)).total_seconds() for
                 start, stop in zip (values, values[1:])]

        if len(delta) < 2: return 0, 0, 0
        return statistics.mean(delta) / self.divisor, statistics.stdev(delta) / self.divisor

    def process_actual_framerate(self, table_def, rows):
        row_id = table_def.partition("|")[2].split(";").index(self.field)
        values = [row[row_id] for row in rows]

        ts = datetime.datetime.fromtimestamp
        fps =  (len(values) - 1) / (ts(values[-1]/1000000) - ts(values[0]/1000000)).total_seconds()

        return fps

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

    def process_keyframe_period(self, table_def, rows):
        from . import graph

        row_id = table_def.partition("|")[2].split(";").index(self.field)
        values = [row[row_id] for row in rows]

        periods = graph.GraphFormat.as_key_frames(values, period=True)
        if not any(periods):
            return 0, 0, 0

        #res = statistics.mean([p for p in periods if p is not None])
        res = statistics.mode(periods)

        return res, 0, 0

    def do_hover(self, meta_value, variables, figure, data, click_info):
        ax = figure['data'][click_info.idx]['xaxis']

        xaxis = 'xaxis' + (ax[1:] if ax != 'x' else '')
        yaxis = figure['layout']['yaxis']['title']['text']

        try: xaxis_name = figure['layout'][xaxis]['title']['text']
        except KeyError: xaxis_name = ''

        props = " ".join([click_info.x, click_info.legend, xaxis_name]).split()
        value = f"{yaxis}: {click_info.y:.2f}"

        return TableStats.props_to_hoverlink(variables, props, value)

    @staticmethod
    def props_to_hoverlink(variables, props, value):
        for prop in props:
            k, v = prop.split('=')
            variables[k] = v

        key = "_".join([f"{k}={variables[k]}" for k in key_order])

        try: entry = Matrix.entry_map[key]
        except KeyError: return f"Error: record '{key}' not found in matrix ..."

        link = html.A("view", target="_blank", href="/viewer/"+entry.linkname)

        return [f"{key.replace('_', ', ')} 🡆 {value} (", link, ")"]

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        data = [[[], []]]
        layout = go.Layout()
        layout.hovermode = 'closest'
        layout.meta = dict(name=self.name),

        if len(variables) == 0:
            layout.title = "Select at least 1 variable parameter..."
            return {'data': data, 'layout': layout}

        *second_vars, legend_var = ordered_vars
        second_vars.reverse()

        layout.title = f"{self.name} vs " + " x ".join(ordered_vars[:-1]) + " | " + ordered_vars[-1]
        layout.yaxis = dict(title=self.name+ f" ({self.unit})")
        layout.plot_bgcolor='rgb(245,245,240)'
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
        legends_visible = []
        for param_values in sorted(itertools.product(*param_lists)):
            params.update(dict(param_values))

            key = "_".join([f"{k}={params[k]}" for k in key_order])

            try: entry = Matrix.entry_map[key]
            except KeyError: continue # missing experiment

            if self.name not in entry.stats:
                print(f"Stats not found: {self.name} for entry '{key}' ")
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
            if len(variables) < 5:
                plot_args['type'] = 'line'
                plot_args['line'] = dict(color=color)
            else:
                plot_args['mode'] = 'markers'
                plot_args['marker'] = dict(color=color)

        def prepare_scatter_short_err(legend_key):
            y_err_above = [];  y_err_below = []
            for _y, _y_error in zip(y[legend_key], y_err[legend_key]):
                # above == below iff len(_y_error) == 1
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
                    if _y is not None:
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
                legendgroup=legend_name + ("(stdev)" if len(variables) >= 4 else ""),
                showlegend=(ax == "x1" and len(variables) >= 4), hoverinfo="skip",
                fill='toself', fillcolor='rgba(0,100,80,0.2)',
                line_color='rgba(0,0,0,0)', xaxis=ax,
                name=legend_name + (" (stdev)" if len(variables) >= 4 else "")
            ))

            return max([yval for yval in [y_max]+y_err_data if yval is not None])

        y_max = 0
        for legend_key in sorted(legend_keys):
            legend_name, subplots_key = legend_key
            ax = subplots[subplots_key]
            has_err = any(y_err[legend_key])

            color = COLORS[list(legend_names).index(legend_name)]
            plot_args = dict()

            if len(variables) <= 2:
                prepare_histogram(legend_key, color)
            else:
                prepare_scatter(legend_key, color)

            if has_err and len(variables) < 5:
                if len(variables) <= 2:
                    err_data = plot_histogram_err(legend_key)
                else:
                    if len(variables) < 4:
                        err_data = prepare_scatter_short_err(legend_key)
                    else:
                        err_data = prepare_scatter_long_err(legend_key)

                    y_max = plot_scatter_err(legend_key, err_data, y_max)


            DO_LOCAL_SORT = True
            if len(variables) >= 5 and DO_LOCAL_SORT:
                # sort x according to y's value order
                x[legend_key] = [_x for _y, _x in sorted(zip(y[legend_key], x[legend_key]),
                                                             key=lambda v: (v[0] is None, v[0]))]
                # sort y by value (that may be None)
                y[legend_key].sort(key=lambda x: (x is None, x))
                if not layout.title.text.endswith(" (sorted)"):
                    layout.title.text += " (sorted)"

            # if 2 >= len(variables) > 5:
            #   need to sort and don't move the None location
            #   need to sort yerr as well

            showlegend = legend_name not in legends_visible
            if showlegend: legends_visible.append(legend_name)

            y_max = max([yval for yval in [y_max]+y[legend_key] if yval is not None])
            data.append(dict(**plot_args, x=x[legend_key], y=y[legend_key],
                             legendgroup=legend_name,
                             xaxis=ax, name=legend_name,
                             showlegend=showlegend, hoverlabel= {'namelength' :-1}))
        if len(variables) > 2:
            # force y_min = 0 | y_max = max visible value (cannot set only y_min)
            # if len(variables) <= 2:
            #   bar plot start from 0, y_max hard to compute with error bars

            layout.yaxis.range = [0, y_max]

        layout.legend.traceorder = 'normal'

        return { 'data': data, 'layout': layout}

for who in "client", "guest":
    Who = who.capitalize()
    Regression(f"fps_vs_{who}_cpu", "framerate", f"FPS vs {Who} CPU", f"{Who} Framerate", f"{Who} CPU")
    Regression(f"fps_vs_{who}_gpu_video", "framerate", f"FPS vs {Who} GPU Video", f"{Who} Framerate", f"{Who} GPU Video")
    Regression(f"fps_vs_{who}_gpu_render", "framerate", f"FPS vs {Who} GPU Render", f"{Who} Framerate", f"{Who} GPU Render")

Regression(f"fps_vs_decode_time", "framerate", f"FPS vs Client Decode Time",
           f"Client Framerate", f"Client Decode time/s")

Regression(f"fps_vs_time_in_queue", "framerate", f"FPS vs Time in Client Queue",
           f"Client Framerate", f"Client time in queue (per second)")

HeatmapPlot("Frame Size/Decoding", 'client.client', "Frame Size vs Decode duration",
            ("client.frame_size", "Frame size (in KB)", 0.001),
            ("client.decode_duration", "Decode duration (in ms)", 1000))

TableStats.KeyFramesSize("keyframe_size", "Frame Size: keyframes", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".0f", "KB", divisor=1000)
TableStats.LowFramesSize("lowframe_size", "Frame Size: lowframes", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".0f", "KB", divisor=1000)
TableStats.KeyLowFramesSize("keylowframe_size", "Frame Size: keys+lows", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".0f", "KB", divisor=1000)

TableStats.PerSecond("frame_size", "Frame Bandwidth", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".2f", "MB/s", min_rows=10, divisor=1000*1000)

TableStats.KeyFramePeriod("keyframe_period", "Keyframe Period", "server.host",
                          "host.frame_size", ".0f", "frames")

TableStats.Average("client_time_in_queue_avg", "Client time in queue (avg)",
                   "client.frames_time_to_drop", "frames_time_to_drop.in_queue_time", ".0f", "ms",
                   divisor=1000)

TableStats.PerSecond("client_time_in_queue_persec", "Client time in queue (per second)", "client.frames_time_to_drop",
                     ("frames_time_to_drop.msg_ts", "frames_time_to_drop.in_queue_time"), ".0f", "ms/sec", divisor=1000)

for name in ("server", "client", "guest"):
    TableStats.Average(f"{name}_gpu_video", f"{name.capitalize()} GPU Video",
                       f"{name}.gpu", "gpu.video", ".0f", "%")
    TableStats.Average(f"{name}_gpu_render", f"{name.capitalize()} GPU Render",
                       f"{name}.gpu", "gpu.render", ".0f",  "%")

    TableStats.Average(f"{name}_cpu", f"{name.capitalize()} CPU", f"{name}.{name}-pid",
                       f"{name}-pid.cpu_user", ".0f", "%")

TableStats.Average(f"client_queue", f"Client Queue", "client.client", "client.queue", ".2f", "")

for agent_name, tbl_name in (("client", "client"), ("guest", "guest"), ("server", "host")):
    TableStats.AvgTimeDelta(f"{agent_name}_frame_delta", f"{agent_name.capitalize()} Frames Δ",
                            f"{agent_name}.{tbl_name}", f"{tbl_name}.msg_ts", ".2f", "ms")
    TableStats.ActualFramerate(f"{agent_name}_framerate", f"{agent_name.capitalize()} Framerate",
                               f"{agent_name}.{tbl_name}", f"{tbl_name}.msg_ts", ".0f", "FPS")

    TableStats.AgentActualFramerate(f"{agent_name}_framerate_agent", f"{agent_name.capitalize()} Agent Framerate",
                                    f"{agent_name}.{tbl_name}", f"{tbl_name}.framerate_actual", ".0f", "fps")

TableStats.PerSecond("client_decode_per_s", "Client Decode time/s", "client.client",
                      ("client.msg_ts", "client.decode_duration"), ".0f", "s/s", min_rows=10, divisor=1000*1000)

TableStats.PerFrame("client_decode_per_f", "Client Decode time/frame", "client.client",
                    ("client.msg_ts", "client.decode_duration"), ".0f", "s/frame", min_rows=10, divisor=1000*1000)

TableStats.Average("client_decode", "Client Decode Duration", "client.client",
                   "client.decode_duration", ".0f", "s")

TableStats.Average(f"guest_send_duration", f"Guest Send Duration", "guest.guest",
                   "guest.send_duration", ".0f", "s")


TableStats.StartStopDiff(f"frames_dropped", f"Client Frames Dropped", "client.frames_dropped",
                         "frames_dropped.count", "d", "frames")
class Matrix():
    properties = defaultdict(set)
    entry_map = {}

    broken_files = []

FileEntry = types.SimpleNamespace
Params = types.SimpleNamespace

key_order = None

def parse_data(filename, reloading=False):
    if not os.path.exists(filename): return
    directory = filename.rpartition(os.sep)[0]
    from . import script_types
    expe = filename[len(script_types.RESULTS_PATH)+1:].partition("/")[0]

    for _line in open(filename).readlines():
        line = _line[:-1].partition("#")[0].strip()
        if not line: continue

        entry = FileEntry()
        entry.params = Params()

        # codec=gst.vp8.vaapivp8enc_record-time=30s_resolution=1920x1080_webpage=cubemap | 1920x1080/cubemap | bitrate=1000_rate-control=cbr_keyframe-period=25_framerate=35.rec

        script_key, file_path, file_key = line.split(" | ")

        entry.key = "_".join([f"experiment={expe}", script_key, file_key])

        entry.params.__dict__.update(dict([kv.split("=") for kv in entry.key.split("_")]))

        global key_order
        if key_order is None:
            key_order = tuple(entry.params.__dict__)

        entry.filename = os.sep.join([directory, file_path, file_key+".rec"])
        entry.linkname = os.sep.join(["results", expe, file_path, file_key+".rec"])

        if not os.path.exists(entry.filename): continue

        try:
            dup_entry = Matrix.entry_map[entry.key]
            if not reloading and dup_entry.filename != entry.filename:
                print(f"WARNING: duplicated key: {entry.key} ({entry.filename})")
                print(f"\t 1: {dup_entry.filename}")
                print(f"\t 2: {entry.filename}")
                continue
        except KeyError: pass # not duplicated

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
                    print("### ", "http://localhost:8050/viewer/"+entry.linkname, msg)
                    Matrix.broken_files.append((entry.filename, entry.linkname + msg))
                    break

            if not keep: break # not enough rows, skip the record
            entry.tables[table_def] = table_name, table_rows

        if table_def is not None: # didn't break because not enough entries
            continue

        for param, value in entry.params.__dict__.items():
            try: value = int(value)
            except ValueError: pass # not a number, keep it as a string
            Matrix.properties[param].add(value)

        Matrix.entry_map[entry.key] = entry

        entry.stats = {}
        for table_def, (table_name, table_rows) in entry.tables.items():
            for table_stat in TableStats.interesting_tables[table_name]:
                entry.stats[table_stat.name] = table_stat.process(table_def, table_rows)

        for table_stat in TableStats.all_stats:
            Matrix.properties["stats"].add(table_stat.name)

    for key, values in Matrix.properties.items():
        print(f"{key:20s}: {', '.join(map(str, values))}")

def build_layout(app, search):
    defaults = urllib.parse.parse_qs(search[1:]) if search else {}

    matrix_controls = [html.B("Parameters:", id="lbl_params"), html.Br()]
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
            attr["searchable"] = False

            if key == "experiment" and "current" in values:
                attr["value"] = "current"
            else:
                attr["value"] = "---"

        try:
            default_value = defaults[key]
            attr["value"] = default_value[0] if len(default_value) == 1 else default_value
        except KeyError: pass

        tag = dcc.Dropdown(id='list-params-'+key, options=options,
                           **attr, clearable=False)

        matrix_controls += [html.Span(f"{key}: ", id=f"label_{key}"), tag]

    config = [html.B("Configuration:", id='config_title'), html.Br(),
              dcc.Input(id='custom_config', placeholder='Config settings', debounce=True),
              html.Div(id='custom_config_saved')]

    aspect = [html.Br(), html.B("Aspect:"), html.Br(),
              dcc.Checklist(id="matrix-show-text", value='',
                            options=[{'label': 'Show text', 'value': 'txt'}]),
              html.Div(defaults.get("property-order", [''])[0], id='property-order')
    ]

    permalink = [html.P(dcc.Link('Permalink', href='', id='permalink'))]
    control_children = matrix_controls + config + aspect + permalink

    graph_children = []
    for table_stat in TableStats.all_stats:
        graph_children += [dcc.Graph(id=table_stat.id_name, style={"display": "none"}, config=dict(showTips=False))]


    graph_children += [html.Div(id="text-box:clientside-output")]

    return html.Div([
        html.Div(children=control_children, className='two columns'),
        html.Div("nothing yet", id='text-box', className='three columns', style=dict(display='none')),
        html.Div(children=graph_children, id='graph-box', className='ten columns'),
        html.P(id="graph-hover-info"),
    ])

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
        key = "_".join([f"{k}={entry_dict[k]}" for k in key_order])

        try: entry = Matrix.entry_map[key]
        except KeyError: continue

        title = " ".join(f"{k}={v}" for k, v in entry_dict.items() if k not in ("params", "stats") and len(params[k]) > 1)
        if not title: title = "Single match"

        link = html.A("view", target="_blank", href="/viewer/"+entry.linkname)

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

# not used, here for reference ...
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

    app.clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="resize_graph"),
        Output("text-box:clientside-output", "children"),
        [Input('text-box', "style"), Input('list-params-stats', "value")],
    )
    @app.callback([Output("text-box", 'style'), Output("graph-box", 'className'),],
                  [Input('matrix-show-text', "value")])
    def show_text(arg):
        if 'txt' in arg:
            return {}, 'seven columns'
        else:
            return dict(display='none'), 'ten columns'

    @app.callback([Output('custom_config_saved', 'children'),
                   Output('custom_config_saved', 'data'),
                   Output('custom_config', 'value')],
                  [Input('config_title', 'n_clicks')],
                  [State('custom_config_saved', 'data'),
                   State('custom_config', 'value')])
    def save_config(*args):
        title_click, data, value = args
        if data is None: data = []

        if not value:
            return dash.no_update, dash.no_update, dash.no_update
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

            data.append(value)

        return list([html.P(e) for e in data]), data, ''

    @app.callback(Output("text-box", 'children'),
                  [Input('list-params-'+key, "value") for key in Matrix.properties])
    def param_changed(*args):
        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

        if triggered_id == "custom_config.value":
            if not config or config.startswith("_"):
                return dash.no_update
            if config_saved and config in config_saved:
                return dash.no_update

        if triggered_id.startswith("list-params-"):
            return process_selection(dict(zip(Matrix.properties, args)))


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
        [Input(table_stat.id_name, 'clickData') for table_stat in TableStats.all_stats],
        [State(table_stat.id_name, 'figure') for table_stat in TableStats.all_stats]
       +[State('list-params-'+key, "value") for key in Matrix.properties])
    def display_hover_data(*args):
        nb_stats = len(TableStats.all_stats)
        hoverData = args[:nb_stats]

        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

        stat_id_name = triggered_id.rpartition(".")[0] # eg: client_framerate_agent.clickData

        pos = [s.id_name for s in TableStats.all_stats].index(stat_id_name)
        data = hoverData[pos]

        figure = args[nb_stats:2*nb_stats][pos]
        variables = dict(zip(Matrix.properties.keys(), args[2*nb_stats:]))

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

    @app.callback(Output("permalink", 'href'),
                  [Input('list-params-'+key, "value") for key in Matrix.properties]
                  +[Input('property-order', 'children')])
    def get_permalink(*args):
        try: triggered_id = dash.callback_context.triggered
        except IndexError: return dash.no_update # nothing triggered the script (on multiapp load)
        params = dict(zip(Matrix.properties.keys(), args[:len(Matrix.properties)]))

        def val(k, v):
            if isinstance(v, list): return "&".join(f"{k}={vv}" for vv in v)
            else: return f"{k}={v}"

        search = "?"+"&".join(val(k, v) for k, v in params.items() \
                            if v not in ('---', None) and len(Matrix.properties[k]) != 1)
        if args[-1]:
            search += f"&property-order={args[-1]}"
        return search


    for _table_stat in TableStats.all_stats:
        def create_callback(table_stat):
            @app.callback(Output(table_stat.id_name, 'style'),
                          [Input('list-params-stats', "value")])
            def graph_style(stats_values):
                try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
                except IndexError: triggered_id = None # nothing triggered the script (on multiapp load)

                if not isinstance(stats_values, list):
                    # only 1 elt in stats_values dropdown, a str is returned instead of a list.
                    # That makes the following silly ...
                    stats_values = [stats_values]

                style = {}
                style["display"] = "block" if triggered_id and table_stat.name in stats_values else "none"
                if style["display"] == "block":
                    print("Show",table_stat.name )
                style["height"] = f"{100/len(stats_values) if stats_values else 100:.2f}vh"

                return style

            @app.callback(Output(table_stat.id_name, 'figure'),
                          [Input('list-params-'+key, "value") for key in Matrix.properties]
                          +[Input("lbl_params", "n_clicks")]+[Input('property-order', 'children')]
                          +[Input('custom_config', 'value'), Input('custom_config_saved', 'data')]
            )
            def graph_figure(*args):
                try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
                except IndexError: return # nothing triggered the script (on multiapp load)

                *args, config, config_saved = args

                if triggered_id == "custom_config.value":
                    if not config or config.startswith("_"):
                        return dash.no_update
                    if config_saved and config in config_saved:
                        return dash.no_update

                cfg = {}
                lst = (config_saved if config_saved else []) + ([config] if config else [])

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
                if not stats_values or table_stat.name not in stats_values:
                    return dash.no_update

                variables = {k:(Matrix.properties[k]) for k, v in params.items() \
                             if k != "stats" and v == "---"}

                ordered_vars = sorted(variables.keys(), key=var_order.index)
                ordered_vars.reverse()

                param_lists = [[(key, v) for v in variables[key]] for key in ordered_vars]

                return table_stat.do_plot(ordered_vars, params, param_lists, variables, cfg)

        # must use internal function to save 'table_stat' closure context
        create_callback(_table_stat)
