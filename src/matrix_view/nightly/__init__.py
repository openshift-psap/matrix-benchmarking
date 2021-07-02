from collections import defaultdict
from datetime import datetime

import plotly.graph_objs as go

from matrix_view.table_stats import TableStats
import matrix_view
from common import Matrix


def register():
    TableStats.ValueDev("speed", "Simulation speed", "speed", ".2f", "ns/day", higher_better=False)
    NightlySpeed()

class NightlySpeed():
    def __init__(self):
        self.name = "Nightly Speed"

        self.id_name = self.name.lower().replace(" ", "_")

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()
        plot_title = "GPU Burn nightly speed"

        plot_values = defaultdict(list)
        entries = []

        dates_speeds = defaultdict(list)
        dates = defaultdict(list)
        names = set()
        y_max = 0
        for entry in Matrix.all_records(params, param_lists):
            def add_plot(an_entry):
                nonlocal y_max
                date_ts = int(an_entry.import_settings["@build-id"])
                date = date_ts#datetime.fromtimestamp(date_ts/1000)
                speed = an_entry.results.speed
                name = ",".join([f"{var}={params[var]}" for var in ordered_vars])
                y_max = max([y_max, speed])
                dates_speeds[name].append([date, speed])
                names.add(name)

            if entry.is_gathered:
                for single_entry in entry.results:
                    add_plot(single_entry)
            else:
                add_plot(entry)

        for name in sorted(names):
            current_dates_speeds = dates_speeds[name]
            current_dates_speeds = sorted(current_dates_speeds)
            dates = [dt_sp[0] for dt_sp in current_dates_speeds]
            speeds = [dt_sp[1] for dt_sp in current_dates_speeds]

            trace = go.Scatter(x=dates, y=speeds,
                               name=name,
                               hoverlabel= {'namelength' :-1},
                               showlegend=True,
                               mode='markers+lines')
            fig.add_trace(trace)

        fig.update_layout(
            yaxis=dict(title='GPU Burn speed',
                       range=[0, y_max*1.05],
                       ),
            title=plot_title, title_x=0.5)
        return fig, ""
