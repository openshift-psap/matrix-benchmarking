from collections import defaultdict
import statistics as stats

import plotly.graph_objs as go

import matrix_view.table_stats
from common import Matrix
from matrix_view import COLORS

class SimpleNet():
    def __init__(self):
        self.name = "OSU Network"
        self.id_name = "osu-network"

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()
        cfg__remove_details = cfg.get('perf.rm_details', False)
        cfg__legend_pos = cfg.get('perf.legend_pos', False)

        if params["operation"] == "---":
            return {}, f"Please select only one benchmark type ({', '.join(variables['operation'])})"
        if params["operation"].startswith("hello"):
            return {}, f"Operation 'hello-hello' is not compatible with OSU network plotting."

        XY = defaultdict(dict)
        XYerr_pos = defaultdict(dict)
        XYerr_neg = defaultdict(dict)

        plot_title = None
        plot_legend = None

        for entry in Matrix.all_records(params, param_lists):
            if plot_title is None:
                results = entry.results[0].results if entry.is_gathered else entry.results
                plot_title = results.osu_title
                plot_legend = results.osu_legend

            legend_name = " ".join([f"{key}={entry.params.__dict__[key]}" for key in variables])

            if entry.is_gathered:
                gather_xy = defaultdict(list)
                for _entry in entry.results:
                    for x, y in _entry.results.measures.items():
                        gather_xy[x].append(y)
                legend_name += " " + " ".join(entry.gathered_keys.keys())
                for x, gather_y in gather_xy.items():
                    XY[legend_name][x] = y = stats.mean(gather_y)
                    err = stats.stdev(gather_y) if len(gather_y) > 2 else 0
                    XYerr_pos[legend_name][x] = y + err
                    XYerr_neg[legend_name][x] = y - err
            else:
                gather_key_name = [k for k in entry.params.__dict__.keys() if k.startswith("@")][0]

                for x, y in entry.results.measures.items():
                    XY[legend_name][x] = y

        if not XY:
            print("Nothing to plot ...", params)
            return None, "Nothing to plot ..."

        data = []
        y_max = 0
        for legend_name in XY:
            x = list(sorted(XY[legend_name].keys()))
            y = list([XY[legend_name][_x] for _x in x])
            y_max = max(y + [y_max])

            color = COLORS(list(XY.keys()).index(legend_name))

            data.append(go.Scatter(name=legend_name,
                                   x=x, y=y,
                                   mode="markers+lines",
                                   line=dict(color=color, width=2),
                                   hoverlabel= {'namelength' :-1},
                                   legendgroup=legend_name,
                                   ))

            if not XYerr_pos: continue

            y_err_pos = list([XYerr_pos[legend_name][_x] for _x in x])
            y_err_neg = list([XYerr_neg[legend_name][_x] for _x in x])

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

        if "MPI Latency" in plot_title:
            plot_title = "OSU MPI Latency Test (lower is better)"
        elif "Bandwidth" in plot_title:
            plot_title = "OSU MPI Bandwidth Test (higher is better)"
        elif "All-to-All" in plot_title:
            plot_title = "OSU MPI All-to-All Latency Test (lower is better)"
        elif "Allreduce" in plot_title:
            plot_title = "OSU MPI AllReduce Latency Test (lower is better)"

        # Edit the layout
        x_title, y_title = plot_legend
        fig.update_layout(title=plot_title, title_x=0.5,
                          xaxis_title="Message "+x_title,
                          yaxis_range=[0, y_max],
                          yaxis_title=y_title)

        return fig, ""
