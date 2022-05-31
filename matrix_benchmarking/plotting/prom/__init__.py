import datetime

import plotly.graph_objs as go

import matrix_benchmarking.plotting.table_stats as table_stats
import matrix_benchmarking.common as common


def default_get_metrics(entry, metric):
    return entry.results.metrics[metric]


class Plot():
    def __init__(self, metric, y_title,
                 get_metrics=default_get_metrics,
                 filter_metrics=lambda x:x,
                 as_timestamp=False):
        self.name = f"Prom: {y_title}"
        self.id_name = f"prom_overview_{metric}"
        self.metric = metric
        self.y_title = y_title
        self.filter_metrics = filter_metrics
        self.get_metrics = get_metrics
        self.as_timestamp = as_timestamp

        table_stats.TableStats._register_stat(self)
        common.Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, settings, param_lists, variables, cfg):
        fig = go.Figure()

        plot_title = f"Prometheus: {self.y_title}<br>({self.metric})"
        y_max = 0
        for entry in common.Matrix.all_records(settings, param_lists):
            for metric in self.filter_metrics(self.get_metrics(entry, self.metric)):
                x_values = [x for x, y in metric["values"]]
                y_values = [float(y) for x, y in metric["values"]]


                pod_name = metric["metric"]["pod"]
                name_key = " ".join([pod_name, "_".join(f"{k}={settings[k]}" for k in ordered_vars)])

                if self.as_timestamp:
                    x_values = [datetime.datetime.fromtimestamp(x) for x in x_values]
                else:
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
