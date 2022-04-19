from collections import defaultdict
import statistics as stats

import plotly.graph_objs as go

import matrix_view.table_stats
from common import Matrix
from matrix_view import COLORS

class Hello():
    def __init__(self):
        self.name = "Hello"
        self.id_name = "Hello"

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()
        cfg__remove_details = cfg.get('perf.rm_details', False)
        cfg__legend_pos = cfg.get('perf.legend_pos', False)
        variables.pop("node_count")

        if params["operation"] == "---":
            return {}, f"Please select only one benchmark type ({', '.join(variables['operation'])})"

        if params["operation"] != "hello-hello":
            return {}, f"Only peration 'hello-hello' is compatible with this plot plotting."

        XY = defaultdict(dict)
        XYerr_pos = defaultdict(dict)
        XYerr_neg = defaultdict(dict)

        for entry in Matrix.all_records(params, param_lists):
            legend_name = " ".join([f"{key}={entry.params.__dict__[key]}" for key in variables])

            if entry.is_gathered:
                y_values = [entry.results.completionTime.seconds for entry in entry.results]
                y = stats.mean(y_values)
                y_err = stats.stdev(y_values) if len(y_values) > 2 else 0

                legend_name += " " + " ".join(entry.gathered_keys.keys()) + f" x{len(entry.results)}"

                XYerr_pos[legend_name][int(entry.params.node_count)] = y + y_err
                XYerr_neg[legend_name][int(entry.params.node_count)] = y - y_err
            else:
                y = entry.results.completionTime.seconds

                gather_key_name = [k for k in entry.params.__dict__.keys() if k.startswith("@")][0]

            XY[legend_name][int(entry.params.node_count)] = y

        y_max = 0
        data = []
        for legend_name in XY:
            x = list(sorted(XY[legend_name].keys()))
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


        if legend_name:
            x = list(sorted(XY[legend_name].keys()))
            y_linear = [_x for _x in x]

            data.append(go.Scatter(name="linear",
                                   x=x, y=y_linear,
                                   mode="lines",
                                   ))

        fig = go.Figure(data=data)
        USE_LOG = True
        if USE_LOG:
            fig.update_xaxes(type="log")
            fig.update_yaxes(type="log")
            import math
            # https://plotly.com/python/reference/layout/yaxis/#layout-yaxis-range
            y_max = math.log(y_max, 10)

        fig.update_layout(title="'echo hello' MPI deployment time", title_x=0.5,
                          showlegend=True,
                          yaxis_range=[0, y_max*1.05],
                          xaxis_title="Number of Pods/Nodes [log scale]",
                          yaxis_title="Time (in seconds, lower is better) [log scale]")

        return fig, ""
