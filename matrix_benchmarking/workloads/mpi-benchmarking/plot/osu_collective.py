from collections import defaultdict
import statistics as stats

import plotly.graph_objs as go

import matrix_view.table_stats
from common import Matrix
from matrix_view import COLORS

class SimpleNet():
    def __init__(self):
        self.name = "OSU Collective"
        self.id_name = "osu-network"

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        if params["node_count"] != "---":
            return {}, f"Please unselect 'node_count' setting."

        variables.pop("node_count")

        if params["operation"] == "---":
            return {}, f"Please select only one benchmark operation ({', '.join(variables['operation'])})"
        if not params["operation"].startswith("collective"):
            return {}, f"Only operations 'collective-*' are compatible with OSU network-collective plotting."

        XY = defaultdict(lambda: defaultdict(list))
        XYerr_pos = defaultdict(dict)
        XYerr_neg = defaultdict(dict)

        plot_title = None
        plot_legend = None

        is_gathered = False
        for entry in Matrix.all_records(params, param_lists):
            if plot_title is None:
                results = entry.results[0].results if entry.is_gathered else entry.results
                plot_title = results.osu_title
                plot_legend = results.osu_legend

            if entry.is_gathered:
                is_gathered = True

                for _entry in entry.results:
                    nb_nodes = int(_entry.params.node_count)
                    for size, time in _entry.results.measures.items():
                        legend_name = f"{size} Bytes"
                        legend_name += " ".join([f"{key}={entry.params.__dict__[key]}" for key in variables])
                        #if nb_nodes not in XY[legend_name]: XY[legend_name][nb_nodes] = []
                        XY[legend_name][nb_nodes].append(time)
            else:
                gather_key_name = [k for k in entry.params.__dict__.keys() if k.startswith("@")][0]

                legend_name_suffix = " ".join([f"{key}={entry.params.__dict__[key]}" for key in variables])

                nb_nodes = int(entry.params.node_count)
                for size, time in entry.results.measures.items():
                    legend_name = f"{size}B | "
                    XY[legend_name + legend_name_suffix][nb_nodes] = time

        if not XY:
            print("Nothing to plot ...", params)
            return None, "Nothing to plot ..."

        y_max = 0
        data = []
        for legend_name in XY:
            x = list(sorted(XY[legend_name].keys()))
            y = list([XY[legend_name][_x] for _x in x])

            if is_gathered:
                y_err_pos = []
                y_err_neg = []
                y_collapsed = []
                for all_y_values in y:
                    _y_collapsed = stats.mean(all_y_values)
                    y_collapsed.append(_y_collapsed)

                    err = stats.stdev(all_y_values) if len(all_y_values) > 2 else 0
                    y_err_pos.append(_y_collapsed + err)
                    y_err_neg.append(_y_collapsed - err)
                y = y_collapsed

            color = COLORS(list(XY.keys()).index(legend_name))
            y_max = max(y + [y_max])

            data.append(go.Scatter(name=legend_name,
                                   x=x, y=y,
                                   mode="markers+lines",
                                   line=dict(color=color, width=2),
                                   hoverlabel= {'namelength' :-1},
                                   legendgroup=legend_name,
                                   ))

            if not is_gathered: continue

            y_max = max(y_err_pos + [y_max])

            data.append(go.Scatter(name=legend_name,
                                   x=x, y=y_err_pos,
                                   line=dict(color=color, width=0),
                                   mode="lines",
                                   showlegend=False,
                                   legendgroup=legend_name,
                                   ))
            data.append(go.Scatter(name=legend_name,
                                   x=x, y=y_err_neg,
                                   showlegend=False,
                                   mode="lines",
                                   fill='tonexty',
                                   line=dict(color=color, width=0),
                                   legendgroup=legend_name,
                                   ))

        fig = go.Figure(data=data)

        if "All-to-All" in plot_title:
            plot_title = "OSU MPI All-to-All Latency Test (lower is better)"
        elif "Allreduce" in plot_title:
            plot_title = "OSU MPI AllReduce Latency Test (lower is better)"

        # Edit the layout

        USE_LOG = True
        if USE_LOG:
            fig.update_xaxes(type="log")
            fig.update_yaxes(type="log")
            import math
            # https://plotly.com/python/reference/layout/yaxis/#layout-yaxis-range
            y_max = math.log(y_max, 10)

        x_title, y_title = plot_legend
        fig.update_layout(title=plot_title, title_x=0.5,
                          yaxis_range=[0, y_max*1.05],
                          xaxis_title="Number of nodes",
                          yaxis_title=y_title)

        return fig, ""
