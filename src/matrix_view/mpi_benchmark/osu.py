from collections import defaultdict
import statistics as stats

import plotly.graph_objs as go

import matrix_view.table_stats
from common import Matrix

class SimpleNet():
    def __init__(self):
        self.name = "OSU Network"
        self.id_name = "osu-network"

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.properties["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()
        cfg__remove_details = cfg.get('perf.rm_details', False)
        cfg__legend_pos = cfg.get('perf.legend_pos', False)

        if isinstance(params["benchmark"], list):
            return None, "Please select only one benchmark type ({', '.join(params['benchmark'])})"

        X = defaultdict(lambda:defaultdict(list))
        plot_title = None
        plot_legend = None
        for entry in Matrix.all_records(params, param_lists):
            if plot_title is None:
                plot_title = entry.results.osu_title

            if plot_legend is None:
                plot_legend = entry.results.osu_legend

            net_name = entry.params.network
            for x, y in entry.results.osu_results.items():
                X[net_name][x].append(float(y))

        if plot_title is None:
            return None, "Nothing to plot ..."

        data = []
        for net_name in sorted(X):
            net_values = X[net_name]

            x = []
            y = []
            err_pos = []
            err_neg = []
            nb_measurements = None
            for x_value, y_values in net_values.items():
                x.append(float(x_value))
                y.append(stats.mean(y_values))
                err_pos.append(y[-1] + (stats.stdev(y_values) if len(y_values) > 2 else 0))
                err_neg.append(y[-1] - (stats.stdev(y_values) if len(y_values) > 2 else 0))
                nb_measurements = len(y_values)

            legend_name = f"{net_name}"

            if not cfg__remove_details:
                legend_name += f" ({nb_measurements} measures)"

            colors = {
                "baremetal": "black",
                "Multus": "red",
                "SDN": "blue",
                "HostNetwork":"green"
            }

            color = colors[net_name]
            data.append(go.Scatter(name=legend_name,
                                   x=x, y=y,
                                   mode="markers+lines",
                                   hoverlabel= {'namelength' :-1},
                                   line=dict(color=color, width=1),
                                   legendgroup=net_name
                                   ))

            data.append(go.Scatter(name=legend_name+color,
                                   x=x, y=err_pos,
                                   line=dict(color=color, width=0),
                                   mode="lines",
                                   legendgroup=net_name,
                                   showlegend=False,
                                   ))
            data.append(go.Scatter(name=legend_name+color,
                                   x=x, y=err_neg,
                                   showlegend=False,
                                   mode="lines",
                                   fill='tonexty',
                                   line=dict(color=color, width=0),
                                   legendgroup=net_name
                                   ))

        fig = go.Figure(data=data)

        if "MPI Latency" in plot_title:
            plot_title = "OSU MPI Latency Test (lower is better)"
        elif "Bandwidth" in plot_title:
            plot_title = "OSU MPI Bandwidth Test (higher is better)"
        elif "All-to-All" in plot_title:
            plot_title = "OSU MPI All-to-All Latency Test (lower is better)"
        elif "Allreduce" in plot_title:
            plot_title = "OSU MPI AllReduce Latency Test (lower is better)"

        # Edit the layout
        x_title, y_title = plot_legend.split(maxsplit=1)
        fig.update_layout(title=plot_title, title_x=0.5,
                           xaxis_title="Message "+x_title,
                           yaxis_title=y_title)

        return fig, ""
