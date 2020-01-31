from collections import defaultdict
import os
import types
import itertools, functools, operator

import scipy
import scipy.stats
import numpy as np

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Output, Input, State, ClientsideFunction
import plotly
import plotly.graph_objs as go
import plotly.subplots
import flask

import urllib.parse
import datetime
import statistics

import measurement.perf_viewer

import re
def atoi(text): return int(text) if text.isdigit() else text
def natural_keys(text): return [atoi(c) for c in re.split(r'(\d+)', str(text))]

PROPERTY_RENAME = {
    # gst.nvenc

    "gop-size": "keyframe-period",
    "rc-mode": "rate-control",

    # native nvidia plugin
    "ratecontrol": "rate-control",
    "max-bitrate": "bitrate",
    "gop": "keyframe-period",
}

VALUE_TRANSLATE = {
    "gop-size": {"-1": "600000"},
}

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

class EncodingStacked():
    def __init__(self):
        self.name = "Stack: Encoding"
        self.id_name = "stack_encoding"

        TableStats._register_stat(self)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing ..."

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()
        layout = go.Layout(meta=dict(name=self.name))

        second_vars = ordered_vars[:]
        second_vars.reverse()

        layout.title = f"{self.name} vs " + " x ".join(ordered_vars)
        layout.plot_bgcolor='rgb(245,245,240)'
        subplots = {}
        if second_vars:
            subplots_var = second_vars[-1]
            subplots_len = len(variables[subplots_var])
            subplots_var_values = sorted(variables[subplots_var], key=natural_keys)

            showticks = len(second_vars) == 2
            for i, subplots_key in enumerate(subplots_var_values):
                subplots[subplots_key] = f"x{i+1}"
                ax = f"xaxis{i+1}"
                layout[ax] = dict(title=f"{subplots_var}={subplots_key}",
                                  domain=[i/subplots_len, (i+1)/subplots_len],
                                  type='category', showticklabels=showticks, tickangle=45)
        else:
            subplots_var = None
            subplots[subplots_var] = "x1"
            layout["xaxis1"] = dict(type='category', showticklabels=False)

        x = defaultdict(list); y = defaultdict(list); y_err = defaultdict(list);
        fps_target = defaultdict(dict);
        fps_actual = defaultdict(dict);

        legend_keys = set()
        legend_names = set()
        legends_visible = []

        show_i_vs_p = bool(cfg.get('stack.i_vs_p'))

        for param_values in sorted(itertools.product(*param_lists)):
            params.update(dict(param_values))

            key = "_".join([f"{k}={params[k]}" for k in key_order])

            try: entry = Matrix.entry_map[key]
            except KeyError: continue # missing experiment

            x_key = " ".join([f'{v}={params[v]}' for v in reversed(second_vars) if v != subplots_var])

            subplots_key = params[subplots_var] if subplots_var else None
            ax = subplots[subplots_key]

            fps_target[ax][x_key] = 1/int(params['framerate']) * 1000 if 'framerate' in params else None
            fps_actual[ax][x_key] = 1/entry.stats["Guest Framerate"].value * 1000

            for what in "sleep", "capture", "encode", "send":
                What = what.title()
                name = f"Guest {What} Duration (avg)"
                if name not in entry.stats:
                    print(f"Stats not found: {name} for entry '{key}' ")
                    continue

                legend_name = f"{What} time"
                legend_key = (legend_name, ax)

                legend_keys.add(legend_key)
                legend_names.add(legend_name)

                def do_add(x_name, y_stat):
                    stats = entry.stats[y_stat]

                    y[legend_key].append(stats.value if stats.value else 0)
                    y_err[legend_key].append(stats.stdev[0] if stats.value else 0)
                    x[legend_key].append(x_name)

                if show_i_vs_p:
                    do_add(x_key + " | all frames", name)
                    do_add(x_key + " | I-frames", name+" I-frames")
                    do_add(x_key + " | P-frames", name+" P-frames")

                    y[legend_key].append(None)
                    y_err[legend_key].append(None)
                    x[legend_key].append("--- "+x_key)
                else:
                    do_add(x_key, name)

        legend_keys = sorted(list(legend_keys), key=natural_keys)
        legend_names = sorted(list(legend_names), key=natural_keys)

        for legend_key in legend_keys:
            legend_name, ax = legend_key

            color = COLORS(list(legend_names).index(legend_name))
            plot_args = dict()

            plot_args['type'] = 'bar'
            plot_args['marker'] = dict(color=color)

            showlegend = legend_name not in legends_visible
            if showlegend: legends_visible.append(legend_name)

            show_err = bool(cfg.get('stack.stdev'))
            fig.add_trace(dict(**plot_args, x=x[legend_key], y=y[legend_key],
                               error_y=dict(type='data', array=y_err[legend_key], visible=show_err),
                             legendgroup=legend_name, name=legend_name, xaxis=ax,
                             showlegend=showlegend, hoverlabel= {'namelength' :-1}))


        framerates = (('Actual FPS', fps_actual, dict(mode='lines+markers', marker=dict(symbol="x", size=10, color="purple"))),
                      ('Target FPS', fps_target, dict(mode='markers', line=dict(color='black'), marker=dict(symbol="cross", size=10, color="black"))),)

        for legend_name, fps_values_dict, mode in framerates if not show_i_vs_p else []:

            for ax, val_dict in fps_values_dict.items():
                showlegend = legend_name not in legends_visible
                if showlegend: legends_visible.append(legend_name)

                fig.add_trace(go.Scatter(x=list(val_dict.keys()), y=list(val_dict.values()), xaxis=ax,
                                         **mode,
                                         name=legend_name, legendgroup=legend_name, showlegend=showlegend, ))

        if x:
            FPS = [30, 40, 45, 60]

            fig.add_trace(go.Scatter(
                x=["_"]*len(FPS), name="FPS indicators",
                y=[1/fps*1000  for fps in FPS],
                mode="text", #marker=dict(symbol="circle", size=7, color="black"),
                text=[f"{fps} FPS" for fps in FPS],
                xaxis=ax,
            ))


        layout.barmode = 'stack'
        fig.update_layout(yaxis=dict(title="Time (in ms)"))
        fig.update_layout(layout)
        return fig, []

class Regression():
    @staticmethod
    def FPS(val):
        "FPS"
        return val

    @staticmethod
    def res_in_pix(res):
        "px" # docstring

        x, y = map(int, res.split("x"))

        return x*y

    def __init__(self, id_name, key_var, name, x_key, y_key):
        self.name = "Reg: " + name
        self.id_name = id_name
        self.x_key = x_key
        self.y_key = y_key
        self.key_var = key_var

        TableStats._register_stat(self)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return ""

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()

        x = defaultdict(list)
        y = defaultdict(list)
        text = defaultdict(list)

        reg_x, reg_y = defaultdict(list), defaultdict(list)

        other_vars = ordered_vars[:]
        try: other_vars.remove(self.key_var)
        except ValueError:
            return { 'data': [], 'layout': dict(title="ERROR: Framerate parameter must be variable ...")}, [""]

        def name_units(ax_key):
            if ax_key.startswith("param:"):
                _, var, *modifiers = ax_key.split(":")
                if not modifiers:
                    unit = 'n/a'
                else:
                    unit = getattr(Regression, modifiers[-1]).__doc__

                return var.title(), unit
            else:
                return ax_key, TableStats.stats_by_name[ax_key].unit

        x_name, x_unit = name_units(self.x_key)
        y_name, y_unit = name_units(self.y_key)

        for param_values in sorted(itertools.product(*param_lists)):
            params.update(dict(param_values))

            key = "_".join([f"{k}={params[k]}" for k in key_order])

            try: entry = Matrix.entry_map[key]
            except KeyError:
                print(f"{key} missing")
                continue # missing experiment

            def value(ax_key):
                if ax_key.startswith("param:"):
                    _, var, *modifiers = ax_key.split(":")
                    val = params[var]
                    for mod in modifiers:
                        val = getattr(Regression, mod)(val)
                    return val
                else:
                    return entry.stats[ax_key].value
            try:
                _x = value(self.x_key)
                _y = value(self.y_key)
            except KeyError:
                print(f"{self.x_key} or {self.y_key} missing values for ", key)
                continue

            legend_key = f"{self.key_var}={params[self.key_var]}"

            reg_key = "all" if not other_vars else \
                 " | ".join(f"{k}={params[k]}" for k in other_vars)

            x[reg_key].append(_x)
            y[reg_key].append(_y)
            text[reg_key].append(legend_key)

            reg_x[reg_key].append(_x)
            reg_y[reg_key].append(_y)

        for i, legend_key in enumerate(x.keys()):
            fig.add_trace(go.Scatter(x=x[legend_key], y=y[legend_key], mode='markers', name=legend_key,
                                     hovertext=text[legend_key],hoverinfo="text+x+y", hoverlabel= {'namelength' :-1},
                                     legendgroup=legend_key,
                                     marker=dict(symbol="cross", size=15, color=COLORS(i))))

        x_title = f"{x_name} ({x_unit})"
        y_title = f"{y_name} ({y_unit})"

        fig.update_layout(yaxis=dict(zeroline=True, showgrid=False, rangemode='tozero',
                                     title=y_title),
                          xaxis=dict(title=x_title))

        x_range = None
        formulae = []
        for i, reg_key in enumerate(reg_x.keys()):
            all_x = reg_x[reg_key]
            all_y = reg_y[reg_key]

            # https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.linregress.html
            slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(all_x, all_y)

            line = slope*np.array(all_x)+intercept
            fig.add_trace(go.Scatter(x=all_x, y=line, mode='lines', hovertext="text",
                                     legendgroup=reg_key,
                                     name=reg_key, line=dict(color=COLORS(i))))

            if not x_range: x_range = [all_x[0], all_x[-1]]
            x_range = [min(x_range[0], min(all_x)), max(x_range[1], max(all_x))]

            # need to change here: if slope/intercept too low, they appear as 0.00 !
            formulae.append(f"{y_name} = {slope:+.2f} * {x_name} {intercept:+.2f} " +
                            f"| r={r_value:+.3f}, p={p_value:+.3f}, stdev={std_err:+.3f} | {reg_key}")

        text_x_pos = x_range[0] + (x_range[1]-x_range[0])/2
        text = '<br>'.join(formulae)

        fig.update_layout(
            meta=dict(name=self.name, value=formulae),
        )

        fig.update_layout(title=f"{y_name} vs {x_name} | {' x '.join(other_vars)}")

        return fig, [html.P(f) for f in formulae]

class Report():
    def __init__(self, id_name, name):
        self.id_name = id_name
        self.name = name
        TableStats._register_stat(self)
        self.no_graph = True

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "" # nothing can be done here ...

    def do_report(self, *args):
        return f"nothing configured to generate the report for {self.name} ..."

    @classmethod
    def Decode(clazz, key_var, *args, **kwargs):
        obj = clazz(f"report_{key_var}_decode", f"Report: Decoding vs {key_var.title()}",
                    *args, **kwargs)

        obj.do_report = lambda *_args: obj.report_decode(key_var, *_args)

        return obj

    @classmethod
    def CPU(clazz, key_var, *args, **kwargs):
        obj = clazz(f"report_{key_var}_cpu", f"Report: Guest/Client CPU vs {key_var.title()}",
                    *args, **kwargs)

        obj.do_report = lambda *_args: obj.report_cpu(key_var, *_args)

        return obj

    @classmethod
    def GPU(clazz, key_var, *args, **kwargs):
        obj = clazz(f"report_{key_var}_gpu", f"Report: Guest/Client GPU vs {key_var.title()}",
                    *args, **kwargs)

        obj.do_report = lambda *_args: obj.report_gpu(key_var, *_args)

        return obj

    @staticmethod
    def prepare_args(args, what, value):
        ordered_vars, params, param_lists, variables, cfg = args

        _ordered_vars = ordered_vars[:]
        try: _ordered_vars.remove(what)
        except ValueError: pass # 'what' wasn't in the list

        _variables = dict(variables)
        if what:
            params[what] = value
            _variables[what] = {value}

        _param_lists = [[(key, v) for v in _variables[key]] for key in ordered_vars]

        return _ordered_vars, params, _param_lists, _variables, cfg

    def do_plot(self, *args):
        ordered_vars, params, param_lists, variables, cfg = args

        print("Generate", self.name, "...")

        header = [html.P("---")]
        for k, v in params.items():
            if k == "stats": continue
            if v != "---": header.insert(0, html.Span([html.B(k), "=", v, ", "]))
            else: header.append(html.P([html.B(k), "=",
                                       ", ".join(map(str, variables[k]))]))
        header += [html.Hr()]
        header.insert(0, html.H1(self.name))

        report = self.do_report(*args)

        print("Generate: done!")

        return {}, header + report

    def report_decode(self, key_var, *args):
        ordered_vars, params, param_lists, variables, cfg = args

        if key_var not in ordered_vars:
            return [f"ERROR: {key_var} must not be set for this report."]

        def do_plot(stat_name, what, value):
            _args = Report.prepare_args(args, what, value)
            reg_stats = TableStats.stats_by_name[stat_name].do_plot(*_args)

            return [dcc.Graph(figure=reg_stats[0])] + reg_stats[1] + [html.Hr()]

        what = ordered_vars[0]
        if what == key_var: what = None
        by_what = f" (by {what})" if what else ""
        # --- Decode time --- #

        report = [html.H2(f"Decode Time" + by_what)]

        for value in variables.get(what, [params[what]]) if what else [""]:
            if what:
                report += [html.P(html.B(f"{what}={value}"))]

            report += do_plot(f"Reg: Client Decode Time vs {key_var.title()}", what, value)

        # --- Decode Time in Queue --- #

        report += [html.H2(f"Time in Queue" + by_what)]

        for value in variables.get(what, [params[what]]) if what else [""]:
            if what:
                report += [html.P(html.B(f"{what}={value}"))]

            report += do_plot(f"Reg: Time in Client Queue vs {key_var.title()}", what, value)

        # --- Client Queue --- #

        report += [html.H2(f"Client Queue Size")]
        report += do_plot("Client Queue", None, None)

        # --- Decode Duration --- #

        report += [html.H2(f"Decode Duration")]
        report += do_plot("Client Decode Duration", None, None)

        # --- Time between arriving frames --- #

        report += [html.H2(f"1/time between arriving frames")]
        report += do_plot("Client Framerate", None, None)

        # --- Frame Bandwidth --- #

        report += [html.H2(f"Frame Bandwidth" + by_what)]

        for value in variables.get(what, [params[what]]) if what else [""]:
            if what:
                report += [html.P(html.B(f"{what}={value}"))]
            report += do_plot(f"Reg: Frame Bandwidth vs {key_var.title()}", what, value)

        return report

    def report_gpu(self, key_var, *args):
        ordered_vars, params, param_lists, variables, cfg = args

        if key_var not in ordered_vars:
            return [ f"ERROR: {key_var} must not be set for this report."]

        def do_plot(stat_name, what, value):
            _args = Report.prepare_args(args, what, value)
            reg_stats = TableStats.stats_by_name[stat_name].do_plot(*_args)

            return [dcc.Graph(figure=reg_stats[0])] + reg_stats[1] + [html.Hr()]

        what = ordered_vars[0]
        if what == key_var: what = None

        # --- GPU --- #
        report = []
        for src in "client", "guest":
            report += [html.H2(f"{src.capitalize()} GPU Usage"+ (f" (by {what})" if what else ""))]

            for value in variables.get(what, [params[what]]) if what else [""]:
                if what:
                    report += [html.P(html.B(f"{what}={value}", what))]

                for gpu in "Render", "Video":
                    report += do_plot(f"Reg: {src.capitalize()} GPU {gpu} vs {key_var.title()}", what, value)

        return report

    def report_cpu(self, key_var, *args):
        ordered_vars, params, param_lists, variables, cfg = args

        if key_var not in ordered_vars:
            return [f"ERROR: {key_var} must not be set for this report."]

        def do_plot(stat_name, what, value):
            _args = Report.prepare_args(args, what, value)
            reg_stats = TableStats.stats_by_name[stat_name].do_plot(*_args)

            return [dcc.Graph(figure=reg_stats[0])] + reg_stats[1] + [html.Hr()]

        what = ordered_vars[0]
        if what == key_var: what = None

        # --- CPU --- #
        report = []

        for src in "client", "guest":
            report += [html.H2(f"{src.capitalize()} CPU Usage" + (f" (by {what})" if what else ""))]

            for value in variables.get(what, [params[what]]) if what else [""]:
                if what:
                    report += [html.P(html.B(f"{what}={value}"))]

                report += do_plot(f"Reg: {src.capitalize()} CPU vs {key_var.title()}", what, value)

        return report

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
                    marker = dict(color = COLORS(i), size = 3 ),
                    name=name, legendgroup=name,
                    x = x, y = y,
                    hoverlabel= {'namelength' :-1}
                ))

            fig.add_trace(go.Histogram(
                xaxis = 'x2', marker = dict(color=COLORS(i)), showlegend=False, opacity=0.75,
                histnorm='percent',
                y = y, legendgroup=name, name=name,
                hoverlabel= {'namelength' :-1},
            ))
            fig.add_trace(go.Histogram(
                yaxis = 'y2', marker = dict(color=COLORS(i)), showlegend=False, opacity=0.75,
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
        return fig, ""


class TableStats():
    all_stats = []
    stats_by_name = {}
    graph_figure = None

    interesting_tables = defaultdict(list)

    @classmethod
    def _register_stat(clazz, stat_obj):
        print(stat_obj.name)

        clazz.all_stats.append(stat_obj)

        if stat_obj.name in clazz.stats_by_name:
            raise Exception(f"Duplicated name: {stat_obj.name}")

        clazz.stats_by_name[stat_obj.name] = stat_obj

    def __init__(self, id_name, name, table, field, fmt, unit, min_rows=0, divisor=1, **kwargs):
        self.id_name = id_name
        self.name = name
        self.table = table
        self.field = field
        self.unit = unit
        self.fmt = fmt
        self.min_rows = min_rows
        self.divisor = divisor
        self.kwargs = kwargs

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
    def KeyFramesCount(clazz, *args, **kwargs):
        obj = clazz(*args, **kwargs)
        obj.do_process = obj.process_keyframes_count
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
                try:
                    v = self.do_process(table_def, rows)
                except Exception as e:
                    print(f"ERROR: Failed to process with {self.do_process}:")
                    print(table_def)
                    print(e)

                    return 0
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
        values = [row[row_id] for row in rows if row[row_id] is not None]

        if not values: return None, None, None

        if "keyframes" in self.kwargs and self.kwargs["keyframes"] is not None:
            kfr_rq = self.kwargs["keyframes"]

            tname = table_def.partition("|")[0].rpartition(".")[-1]
            if f"{tname}.key_frame" not in table_def:
                # no keyframe indicator ...
                return 0, 0

            kfr_row_id = table_def.partition("|")[2].split(";").index(f"{tname}.key_frame")
            kfr_values = [bool(row[kfr_row_id]) for row in rows if row[row_id] is not None]

            if self.field == "guest.sleep_duration":
                # the sleep_duration after encoding a (key)frame is stored in the next row
                # this hook correctly links sleep time and encode time.
                values = [v for v, kfr in zip(values[1:], kfr_values) if (kfr_rq is kfr)]
            else:
                values = [v for v, kfr in zip(values, kfr_values) if (kfr_rq is kfr)]

        if not values:
            return 0, 0

        mean = statistics.mean(values) / self.divisor

        if self.kwargs.get("invert"):
            return 1/mean, 0

        return mean, (statistics.stdev(values) / self.divisor)

    def process_keyframes_count(self, table_def, rows):
        kfr_row_id = table_def.partition("|")[2].split(";").index(self.field)
        kfr_values = [bool(row[kfr_row_id]) for row in rows]

        kfr_cnt = sum(kfr_values)

        return kfr_cnt if self.kwargs["keyframes"] else len(rows) - kfr_cnt

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
        data = []
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
            for i, subplots_key in enumerate(sorted(variables[subplots_var], key=natural_keys)):
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
        legend_keys = sorted(list(legend_keys), key=natural_keys)
        legend_names = sorted(list(legend_names), key=natural_keys)

        for legend_key in legend_keys:
            legend_name, subplots_key = legend_key
            ax = subplots[subplots_key]
            has_err = any(y_err[legend_key])

            color = COLORS(list(legend_names).index(legend_name))
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

        return { 'data': data, 'layout': layout}, [""]

for what in "framerate", "resolution":
    Report.CPU(what)
    Report.GPU(what)
    Report.Decode(what)

EncodingStacked()

for who in "client", "guest":
    Who = who.capitalize()
    for what_param, what_x in ("framerate", f"{Who} Framerate"), ("resolution", "param:resolution:res_in_pix"):
        for y_name in "CPU", "GPU Video", "GPU Render":
            y_id = y_name.lower().replace(" ", "_")
            Regression(f"{what_param}_vs_{who}_{y_id}", what_param, f"{Who} {y_name} vs {what_param.title()}", what_x, f"{Who} {y_name}")

for what_param, what_x in ("framerate", f"Client Framerate"), ("resolution", "param:resolution:res_in_pix"):
    Regression(f"{what_param}_vs_decode_time", what_param, f"Client Decode Time vs {what_param.title()}",
               what_x, f"Client Decode time/s")

    Regression(f"{what_param}_vs_time_in_queue", what_param, f"Time in Client Queue vs {what_param.title()}",
               what_x, f"Client time in queue (per second)")

    if what_x == "Client Framerate": what_x = "param:framerate:FPS"
    Regression(f"{what_param}_vs_bandwidth", what_param, f"Frame Bandwidth vs {what_param.title()}",
               what_x, f"Frame Size (avg)")

HeatmapPlot("Frame Size/Decoding", 'client.client', "Frame Size vs Decode duration",
            ("client.frame_size", "Frame size (in KB)", 0.001),
            ("client.decode_duration", "Decode duration (in ms)", 1000))

TableStats.PerSecond("frame_size_per_sec", "Frame Bandwidth (per sec)", "server.host",
                      ("host.msg_ts", "host.frame_size"), ".2f", "MB/s", min_rows=10, divisor=1000*1000)

TableStats.Average("frame_size", "Frame Size (avg)", "server.host",
                   "host.frame_size", ".2f", "KB", min_rows=10, divisor=1000)

TableStats.KeyFramesCount("keyframe_count", "Keyframe count", "guest.guest",
                          "guest.key_frame", ".0f", "#", keyframes=True)
TableStats.KeyFramesCount("p_frame_count", "P-frame count", "guest.guest",
                          "guest.key_frame", ".0f", "#", keyframes=False)

TableStats.Average("client_time_in_queue_avg", "Client time in queue (avg)",
                   "client.frames_time_to_drop", "frames_time_to_drop.in_queue_time", ".0f", "ms",
                   divisor=1000)

for what in "sleep", "capture", "encode", "send":
    invert = False
    for kfr, kfr_txt in (True, "I-frames"), (False, "P-frames"), (None, ""):
        TableStats.Average(f"guest_{what}_duration_{kfr_txt}", f"Guest {what.capitalize()} Duration (avg){' ' if kfr_txt else ''}{kfr_txt}",
                           "guest.guest", f"guest.{what}_duration", ".0f", "FPS" if invert else "ms", invert=invert, keyframes=kfr, divisor=1 if invert else 1/1000)


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

TableStats.ActualFramerate(f"guest_capture_framerate", f"Guest Capture Framerate",
                           f"guest.capture", f"capture.msg_ts", ".0f", "FPS")

TableStats.PerSecond("client_decode_per_s", "Client Decode time/s", "client.client",
                      ("client.msg_ts", "client.decode_duration"), ".0f", "s/s", min_rows=10, divisor=1000*1000)

TableStats.PerFrame("client_decode_per_f", "Client Decode time/frame", "client.client",
                    ("client.msg_ts", "client.decode_duration"), ".0f", "s/frame", min_rows=10, divisor=1000*1000)

TableStats.Average("client_decode", "Client Decode Duration", "client.client",
                   "client.decode_duration", ".0f", "s")


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
    expe_name = expe.replace("_", "-")

    for _line in open(filename).readlines():
        line = _line[:-1].partition("#")[0].strip()
        if not line: continue

        entry = FileEntry()
        entry.params = Params()

        # codec=gst.vp8.vaapivp8enc_record-time=30s_resolution=1920x1080_webpage=cubemap | 1920x1080/cubemap | bitrate=1000_rate-control=cbr_keyframe-period=25_framerate=35.rec

        script_key, file_path, file_key = line.split(" | ")
        entry_key = "_".join([f"experiment={expe_name}", script_key, file_key])

        for kv in entry_key.split("_"):
            k, v = kv.split("=")

            v = VALUE_TRANSLATE.get(k, {}).get(v, v)
            k = PROPERTY_RENAME.get(k, k)
            entry.params.__dict__[k] = v

        global key_order
        if key_order is None:
            key_order = tuple(entry.params.__dict__)

        entry.key = "_".join([f"{k}={entry.params.__dict__.get(k)}" for k in key_order])

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
    for key, values in Matrix.properties.items():
        Matrix.properties[key] = sorted(values, key=natural_keys)
        print(f"{key:20s}: {', '.join(map(str, Matrix.properties[key]))}")

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
                serial_params # [Input('list-params-'+key, "value") for key in Matrix.properties]
                + [0] # Input("lbl_params", "n_clicks")
                + defaults.get("property-order", ['']) # Input('property-order', 'children')
                + [None] # Input('config-title', 'n_clicks') | None->not clicked yet
                + [''] # Input('custom-config', 'value')
                + [''] # Input('custom-config-saved', 'data')
                + [defaults.get("cfg", [''])] # State('custom-config-saved', 'data-label')
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

    @app.callback(Output("text-box", 'children'),
                  [Input('list-params-'+key, "value") for key in Matrix.properties])
    def param_changed(*args):
        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

        if triggered_id == "custom-config.value":
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
        [Input(graph_id, 'clickData') for graph_id in GRAPH_IDS],
        [State(graph_id, 'figure') for graph_id in GRAPH_IDS]
       +[State('list-params-'+key, "value") for key in Matrix.properties])
    def display_hover_data(*args):
        hoverData = args[:NB_GRAPHS]

        try: triggered_id = dash.callback_context.triggered[0]["prop_id"]
        except IndexError: return # nothing triggered the script (on multiapp load)

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
                    or not triggered_id):
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
                    print(dash.callback_context.triggered)
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
