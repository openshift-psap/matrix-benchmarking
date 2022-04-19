from collections import defaultdict
import statistics as stats
import datetime

import plotly.graph_objs as go

import matrix_benchmarking.plotting.table_stats as table_stats
from matrix_benchmarking.common import Matrix
from matrix_benchmarking.plotting.ui import COLORS

def register():
    Plot("Date")
    Plot("Memfree")
    Plot("Procs")

class Plot():
    def __init__(self, name):
        self.name = name
        self.id_name = name

        table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()

        if params["operation"] == "---":
            return {}, f"Please select only one benchmark type ({', '.join(variables['operation'])})"

        if self.name == "Date" and params["operation"] != "date-date":
            return {}, f"Only operation 'date-date' is compatible with this plot plotting."
        elif self.name == "Memfree" and not params["operation"].startswith("memfree"):
            return {}, f"Operation '{params['operation']}' is not compatible with Memfree plotting."
        elif self.name == "Procs" and not params["operation"].startswith("procs"):
            return {}, f"Operation '{params['operation']}' is not compatible with Procs plotting."

        XY = defaultdict(dict)
        XYerr_pos = defaultdict(dict)
        XYerr_neg = defaultdict(dict)

        if self.name == "Date":
            y_key = lambda results: results.date_ts
        elif self.name == "Procs":
            y_key = lambda results: results.procs
        elif self.name == "Memfree":
            y_key = lambda results: results.memfree

        x_key = lambda entry: int(entry.params.node_count)
        variables.pop("node_count")

        is_gathered = False
        for entry in Matrix.all_records(params, param_lists):
            legend_name = " ".join([f"{key}={entry.params.__dict__[key]}" for key in variables])

            if entry.is_gathered:
                is_gathered = True

                y_values = [y_key(entry.results) for entry in entry.results]

                y = stats.mean(y_values)
                y_err = stats.stdev(y_values) if len(y_values) > 2 else 0

                legend_name += " " + " ".join(entry.gathered_keys.keys()) + f" x{len(entry.results)}"

                if self.name == "Date":
                    XYerr_pos[legend_name][x_key(entry)] = y_err
                    XYerr_neg[legend_name][x_key(entry)] = y_err
                else:
                    XYerr_pos[legend_name][x_key(entry)] = y + y_err
                    XYerr_neg[legend_name][x_key(entry)] = y - y_err
            else:
                y = key(entry.results)

            XY[legend_name][x_key(entry)] = y

        if self.name == "Date":
            y_max = datetime.datetime.now()
        else:
            y_max = 0

        data = []
        for legend_name in XY:
            x = list(sorted(XY[legend_name].keys()))
            if self.name == "Date":
                y = list([datetime.datetime.fromtimestamp(XY[legend_name][_x]) for _x in x])
            else:
                y = list([XY[legend_name][_x] for _x in x])
            y_max = max(y + [y_max])

            color = COLORS(list(XY.keys()).index(legend_name))

            data.append(go.Scatter(name=legend_name,
                                   x=x, y=y,
                                   mode="markers+lines",
                                   line=dict(color=color, width=1),
                                   hoverlabel= {'namelength' :-1},
                                   legendgroup=legend_name,
                                   ))

            if not XYerr_pos: continue
            if self.name == "Date":
                y_err_pos = list([_y + datetime.timedelta(seconds=XYerr_pos[legend_name][_x]) for _x, _y in zip(x, y)])
                y_err_neg = list([_y - datetime.timedelta(seconds=XYerr_neg[legend_name][_x]) for _x, _y in zip(x, y)])
            else:
                y_err_pos = list([XYerr_pos[legend_name][_x] for _x in x])
                y_err_neg = list([XYerr_neg[legend_name][_x] for _x in x])

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
        log_scale = cfg.get("log-scale", False) == "y"

        if log_scale:
            fig.update_xaxes(type="log")
            fig.update_yaxes(type="log")
            import math
            # https://plotly.com/python/reference/layout/yaxis/#layout-yaxis-range
            y_max = math.log(y_max, 10)


        if self.name == "Date":
            fig.update_layout(title="Deployment time", title_x=0.5,
                              showlegend=True,
                              xaxis_title="Number of Pods/Nodes" + (" [log scale]" if log_scale else ""),
                              yaxis_title="Time (in seconds, lower is better)" + (" [log scale]" if log_scale else ""),
                              )
        elif self.name == "Procs":
            fig.update_layout(title="Number of processes running", title_x=0.5,
                              showlegend=True,
                              xaxis_title="Number of Pods/Nodes" + (" [log scale]" if log_scale else ""),
                              yaxis_title="Number of processes running (lower is better)" + (" [log scale]" if log_scale else ""),
                              )
        elif self.name == "Memfree":
            fig.update_layout(title="System free memory", title_x=0.5,
                              showlegend=True,
                              xaxis_title="Number of Pods/Nodes" + (" [log scale]" if log_scale else ""),
                              yaxis_title="Memory free (in Bytes, higher is better)" + (" [log scale]" if log_scale else ""),
                              )


        return fig, ""
