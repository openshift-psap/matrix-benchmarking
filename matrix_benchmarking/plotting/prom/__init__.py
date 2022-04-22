import plotly.graph_objs as go

import matrix_benchmarking.plotting.table_stats as table_stats
import matrix_benchmarking.common as common

class Plot():
    def __init__(self, metric, y_title):
        self.name = f"Prom: {metric}"
        self.id_name = f"prom_overview_{metric}"
        self.metric = metric
        self.y_title = y_title

        table_stats.TableStats._register_stat(self)
        common.Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, settings, param_lists, variables, cfg):
        fig = go.Figure()

        plot_title = f"Prometheus: {self.metric} (overview)"
        y_max = 0
        for entry in common.Matrix.all_records(settings, param_lists):
            for metric in entry.results.metrics[self.metric]:
                if "run-bert" not in metric["metric"].get("exported_pod", ""):
                    continue

                x_values = [x for x, y in metric["values"]]
                y_values = [float(y) for x, y in metric["values"]]

                name_key = "_".join(f"{k}={settings[k]}" for k in ordered_vars)

                x_start = x_values[0]
                x_values = [x-x_start for x in x_values]

                y_max = max([y_max]+y_values)

                trace = go.Scatter(x=x_values, y=y_values,
                                   name=name_key,
                                   hoverlabel= {'namelength' :-1},
                                   showlegend=True,
                                   mode='markers+lines')
                fig.add_trace(trace)

        fig.update_layout(
            title=plot_title, title_x=0.5,
            yaxis=dict(title=self.y_title, range=[0, y_max*1.05]),
            xaxis=dict(title=f"Time (in s)"))

        return fig, ""
