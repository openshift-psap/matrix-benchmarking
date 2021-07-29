from collections import defaultdict
from datetime import datetime

import plotly.graph_objs as go

from matrix_view.table_stats import TableStats
import matrix_view
from common import Matrix


def register():
    TableStats.ValueDev("speed", "Simulation speed", "speed", ".2f", "ns/day", higher_better=False)
    NightlyPlot(key="speed")
    NightlyPlot(key="step_count")
    NightlyPlot(key="ansible_tasks_ok")
    NightlyPlot(key="test_passed")

class NightlyPlot():
    def __init__(self, key):
        self.key = key
        self.name = "Nightly " + self.key.replace("_", " ").title()

        self.id_name = self.name.lower().replace(" ", "_")

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        # would be nice to be able to compute a link to the test results here
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()
        plot_title = self.name

        plot_values = defaultdict(list)
        entries = []

        dates_values = defaultdict(list)
        dates = defaultdict(list)
        names = set()
        y_max = 0
        for entry in Matrix.all_records(params, param_lists):
            def add_plot(an_entry):
                nonlocal y_max

                date_str = an_entry.import_settings["@finish-date"]
                date = datetime.strptime(date_str, '%Y-%m-%d %H:%M')

                try:
                    value = an_entry.results.__dict__[self.key]
                except KeyError: return

                name = ",".join([f"{var}={params[var]}" for var in ordered_vars if var != "benchmark"])
                y_max = max([y_max, value])
                dates_values[name].append([date, value])
                names.add(name)

            if entry.is_gathered:
                for single_entry in entry.results:
                    add_plot(single_entry)
            else:
                add_plot(entry)

        for name in sorted(names):
            current_dates_values = dates_values[name]
            current_dates_values = sorted(current_dates_values)
            dates = [dt_sp[0] for dt_sp in current_dates_values]
            values = [dt_sp[1] for dt_sp in current_dates_values]

            trace = go.Scatter(x=dates, y=values,
                               name=name,
                               hoverlabel= {'namelength' :-1},
                               showlegend=True,
                               mode='markers+lines')
            fig.add_trace(trace)

        fig.update_layout(
            yaxis=dict(title=self.key,
                       range=[0, y_max*1.05],
                       ),
            title=plot_title, title_x=0.5)
        return fig, ""
