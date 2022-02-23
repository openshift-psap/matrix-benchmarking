from collections import defaultdict
import statistics as stats
import datetime

import plotly.graph_objs as go

import matrix_view.table_stats
from common import Matrix
from matrix_view import COLORS

def register():
    Plot("Plot")

class Plot():
    def __init__(self, name):
        self.name = name
        self.id_name = name

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()

        first = True
        title = "N/A"
        scale = "N/A"
        lower_better = None
        XY = dict()
        for entry in Matrix.all_records(params, param_lists):
            XY[entry.results.Arguments] = entry.results.Data_Value
            if first:
                title = entry.results.Description
                scale = entry.results.Scale
                lower_better = entry.results.Proportion == "LIB"
            pass

        data = [go.Bar(x=list(XY.keys()), y=list(XY.values()))]


        fig = go.Figure(data=data)


        fig.update_layout(title=title, title_x=0.5,
                          showlegend=False,
                          yaxis_title=scale + " " + ("(lower is better)" if lower_better else "(higher is better)"),
                          )


        return fig, ""
