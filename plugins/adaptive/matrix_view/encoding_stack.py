from collections import defaultdict

import plotly.graph_objs as go
import plotly.subplots

from ui.table_stats import TableStats
from ui.matrix_view import natural_keys, COLORS
from ui import matrix_view

class EncodingStack():
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

        show_i_vs_p = cfg.get('stack.i_vs_p', [])
        try: show_i_vs_p = show_i_vs_p.lower()
        except AttributeError: pass

        title = f"{self.name} vs " + " x ".join(ordered_vars)

        if show_i_vs_p in (1, "p", "ip"):
            title += " | I-frames"
        if show_i_vs_p in (1, "p", "ip"):
            title += " | P-frames"
        layout.title = title

        layout.plot_bgcolor='rgb(245,245,240)'
        subplots = {}
        if second_vars:
            subplots_var = second_vars[-1]
            subplots_var_values = sorted(variables[subplots_var], key=natural_keys)

            showticks = len(second_vars) == 2
            for i, subplots_key in enumerate(subplots_var_values):
                subplots[subplots_key] = f"x{i+1}"
                ax = f"xaxis{i+1}"
                layout[ax] = dict(title=f"{subplots_var}={subplots_key}",
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

        subplots_used = set()

        for entry in matrix_view.all_records(params, param_lists):
            x_key = " ".join([f'{v}={params[v]}' for v in reversed(second_vars) if v != subplots_var])

            subplots_key = params[subplots_var] if subplots_var else None
            ax = subplots[subplots_key]
            subplots_used.add(ax)

            fps_target[ax][x_key+"-capture"] = 1/int(params['framerate']) * 1000 if 'framerate' in params else None
            fps_actual[ax][x_key+"-send"] = 1/entry.stats["Guest Framerate"].value * 1000

            CAPTURE_STACK = ["capture", "push"]
            SEND_STACK = ["sleep", "pull", "send"]

            for what in CAPTURE_STACK + SEND_STACK:
                What = what.title()
                name = f"Guest {What} Duration (avg)"
                if name not in entry.stats:
                    print(f"Stats not found: {name} for entry '{entry.key}' ")
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
                    if show_i_vs_p in [1]:
                        do_add(x_key + " | all frames", name)
                    if show_i_vs_p in (1, "i", "ip"):
                        do_add(x_key + " | I-frames", name+" I-frames")
                    if show_i_vs_p in (1, "p", "ip"):
                        do_add(x_key + " | P-frames", name+" P-frames")


                    if show_i_vs_p in (1, "ip"):
                        y[legend_key].append(None)
                        y_err[legend_key].append(None)
                        x[legend_key].append("--- "+x_key)
                else:
                    x_key_ = x_key + ("-capture" if what in CAPTURE_STACK else ("-send" if what in SEND_STACK else "-xxx"))
                    do_add(x_key_, name)


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


        framerates = (('Actual FPS', fps_actual, dict(mode='markers', marker=dict(symbol="x", size=10, color="purple"))),
                      ('Target FPS', fps_target, dict(mode='markers', line=dict(color='black'), marker=dict(symbol="cross", size=10, color="black"))),)

        for legend_name, fps_values_dict, mode in framerates if not show_i_vs_p else []:

            for ax, val_dict in fps_values_dict.items():
                showlegend = legend_name not in legends_visible
                if showlegend: legends_visible.append(legend_name)

                fig.add_trace(go.Scatter(x=list(val_dict.keys()), y=list(val_dict.values()), xaxis=ax,
                                         **mode,
                                         name=legend_name, legendgroup=legend_name, showlegend=showlegend, ))

        if x:
            FPS = [40, 45, 60]

            fig.add_trace(go.Scatter(
                x=["_"]*len(FPS), name="FPS indicators",
                y=[1/fps*1000  for fps in FPS],
                mode="text", #marker=dict(symbol="circle", size=7, color="black"),
                text=[f"{fps} FPS" for fps in FPS],
                xaxis=ax,
            ))

        for i, ax in enumerate(sorted(subplots_used)):
            axis = "xaxis"+ax[1:]
            layout[axis].domain = [i/len(subplots_used), (i+1)/len(subplots_used)]
            sort_pipeline = bool(cfg.get('stack.sort_pipeline', True))
            if sort_pipeline:
                elts = []
                for k, v in x.items():
                    if k[1] != ax: continue
                    elts += v

                layout[axis].categoryorder = 'array'
                layout[axis].categoryarray = sorted(elts, key=natural_keys)

        layout.barmode = 'stack'
        fig.update_layout(yaxis=dict(title="Time (in ms)"))
        fig.update_layout(layout)
        return fig, []
