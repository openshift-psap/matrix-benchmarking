from collections import defaultdict
import statistics as stats
import datetime
from collections import OrderedDict

import plotly.graph_objs as go

import matrix_benchmarking.plotting.table_stats as table_stats
from matrix_benchmarking.common import Matrix
from matrix_benchmarking.plotting.ui import COLORS

def register():
    Plot("Plot")

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

        first = True
        title = "N/A"
        scale = "N/A"
        lower_better = None
        system_XY = defaultdict(dict)
        system_highlight = params["system"]
        single_argument = "argument" not in variables

        if params["benchmark"] == "---":
            return {}, f"Please select only one benchmark"


        if system_highlight:
            syst_params = []

            for syst in Matrix.settings["system"]:
                syst_params.append(["system", syst])

            param_lists.append(syst_params)


        for entry in Matrix.all_records(params, param_lists):
            key = entry.params.system if single_argument else entry.results.Arguments
            if key == "N/A": key = ""

            system_XY[entry.params.system][key] = entry.results.Data_Value
            if first:
                title = entry.results.Description
                scale = entry.results.Scale
                lower_better = entry.results.Proportion == "LIB"
                first = False

        if system_highlight != "---" and cfg.get("first", "") == "y":
            val = system_XY.pop(system_highlight)
            system_XY[system_highlight] = val

        data = []
        for system, XY in system_XY.items():
            text = [f"{x:.2f} {scale}" for x in XY.values()]

            if system_highlight == system:
                color = "darkcyan"
            elif system_highlight == "---":
                color = None
            else:
                color = "darkblue"

            data += [go.Bar(name=system,
                            y=list(XY.keys()), x=list(XY.values()), text=text,
                            textfont_size=25,
                            marker_color=color,
                            hoverlabel= {'namelength' :-1},
                            orientation="h")]

        fig = go.Figure(data=data)

        if single_argument and params['argument'] != "N/A":
            title += f"<br>{params['argument']}"
        if system_highlight != "---" and not single_argument:
            title += f"<br>system: {system_highlight}"

        xaxis_title = f"⇦ {scale}, fewer is better" if lower_better else f"⇨ {scale}, more is better"
        fig.update_layout(title=title, title_x=0.5,
                          showlegend=(not single_argument),
                          xaxis_title=xaxis_title,
                          xaxis_ticksuffix=" "+scale,
                          paper_bgcolor='rgb(248, 248, 255)',
                          plot_bgcolor='rgb(248, 248, 255)',
                          )

        fig.update_xaxes(showline=True, linewidth=2, linecolor='gray')
        fig.update_yaxes(showline=True, linewidth=2, linecolor='gray')
        fig.update_xaxes(showgrid=True, gridwidth=2, gridcolor='darkgray')
        fig.update_yaxes(showgrid=False)

        return fig, ""
