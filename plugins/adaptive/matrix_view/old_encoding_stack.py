from collections import defaultdict

import plotly.graph_objs as go
import plotly.subplots

from ui.table_stats import TableStats
from ui.matrix_view import natural_keys, COLORS
from ui import matrix_view

class OldEncodingStack():
    def __init__(self):
        self.name = "Stack: Encoding (old)"
        self.id_name = "old_stack_encoding"

        TableStats._register_stat(self)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing ..."

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()
        layout = go.Layout(meta=dict(name=self.name))

        second_vars = ordered_vars[:]
        second_vars.reverse()

        layout.title = f"{self.name} vs " + " x ".join(ordered_vars[:-1]) + " | " + ordered_vars[-1]
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

        x = defaultdict(list); y = defaultdict(list);
        fps_target = defaultdict(dict);
        fps_actual = defaultdict(dict);

        legend_keys = set()
        legend_names = set()
        legends_visible = []

        for entry in matrix_view.all_records(params, param_lists):
            x_key = " ".join([f'{v}={params[v]}' for v in reversed(second_vars) if v != subplots_var])

            subplots_key = params[subplots_var] if subplots_var else None
            ax = subplots[subplots_key]

            fps_target[ax][x_key] = 1/params['framerate']
            fps_actual[ax][x_key] = 1/entry.stats["Guest Framerate"].value

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
                x[legend_key].append(x_key)
                y[legend_key].append(entry.stats[name].value)


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

            fig.add_trace(dict(**plot_args, x=x[legend_key], y=y[legend_key],
                             legendgroup=legend_name, name=legend_name, xaxis=ax,
                             showlegend=showlegend, hoverlabel= {'namelength' :-1}))

        for legend_name, fps_values_dict, mode in (('Actual FPS', fps_actual, dict(mode='lines+markers', marker=dict(symbol="x", size=10, color="purple"))),
                                                   ('Target FPS', fps_target, dict(mode='markers', line=dict(color='black'), marker=dict(symbol="cross", size=10, color="black"))),):

            for ax, val_dict in fps_values_dict.items():
                showlegend = legend_name not in legends_visible
                if showlegend: legends_visible.append(legend_name)

                fig.add_trace(go.Scatter(x=list(val_dict.keys()), y=list(val_dict.values()), xaxis=ax,
                                         **mode,
                                         name=legend_name, legendgroup=legend_name, showlegend=showlegend, ))

        layout.barmode = 'stack'
        fig.update_layout(yaxis=dict(title="Time (in s)"))
        fig.update_layout(layout)
        return fig, []
