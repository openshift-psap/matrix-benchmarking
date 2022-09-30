import datetime

import plotly.graph_objs as go

import matrix_benchmarking.plotting.table_stats as table_stats
import matrix_benchmarking.common as common


def default_get_metrics(entry, metric):
    return entry.results.metrics[metric]


class Plot():
    def __init__(self, metrics, y_title,
                 get_metrics=default_get_metrics,
                 filter_metrics=lambda entry, metrics: metrics,
                 as_timestamp=False,
                 container_name="all",
                 is_memory=False,
                 is_cluster=False,
                 ):

        self.name = f"Prom: {y_title}"

        self.id_name = f"prom_overview_{y_title}"
        self.metrics = metrics
        self.y_title = y_title
        self.filter_metrics = filter_metrics
        self.get_metrics = get_metrics
        self.as_timestamp = as_timestamp
        self.container_name = container_name
        self.is_memory = is_memory
        self.is_cluster = is_cluster

        table_stats.TableStats._register_stat(self)
        common.Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, settings, param_lists, variables, cfg):
        fig = go.Figure()
        metric_names = [
            list(metric.items())[0][0] if isinstance(metric, dict) else metric
            for metric in self.metrics
        ]

        plot_title = f"Prometheus: {self.y_title}"
        y_max = 0

        y_divisor = 1024*1024*1024 if self.is_memory else 1

        for entry in common.Matrix.all_records(settings, param_lists):
            for metric in self.metrics:
                metric_name, metric_query = list(metric.items())[0] if isinstance(metric, dict) else (metric, metric)

                for metric in self.filter_metrics(entry, self.get_metrics(entry, metric_name)):
                    if not metric: continue

                    x_values = [x for x, y in metric["values"]]
                    y_values = [float(y)/y_divisor for x, y in metric["values"]]

                    metric_actual_name = metric["metric"].get("__name__", metric_name)
                    legend_name = metric_actual_name
                    if metric["metric"].get("container") == "POD": continue

                    legend_group = metric["metric"].get("pod") + "/" + metric["metric"].get("container", self.container_name) \
                        if not self.is_cluster else None

                    if self.as_timestamp:
                        x_values = [datetime.datetime.fromtimestamp(x) for x in x_values]
                    else:
                        x_start = x_values[0]
                        x_values = [x-x_start for x in x_values]

                    y_max = max([y_max]+y_values)

                    opts = {}

                    if self.is_memory and "node" not in metric["metric"]:
                        continue

                    if "requests" in metric_actual_name:
                        opts["line_color"] = "orange"
                        opts["line_dash"] = "dot"
                        opts["mode"] = "lines"

                    elif "limits" in metric_actual_name or "capacity" in metric_actual_name:
                        opts["line_color"] = "red"
                        opts["mode"] = "lines"
                        opts["line_dash"] = "dash"
                    else:
                        opts["mode"] = "markers+lines"

                    trace = go.Scatter(x=x_values, y=y_values,
                                       name=legend_name,
                                       hoverlabel= {'namelength' :-1},
                                       showlegend=True,
                                       legendgroup=legend_group,
                                       legendgrouptitle_text=legend_group,
                                       **opts)
                    fig.add_trace(trace)

        fig.update_layout(
            title=plot_title, title_x=0.5,
            yaxis=dict(title=self.y_title + (" (in Gi)" if self.is_memory else ""), range=[0, y_max*1.05]),
            xaxis=dict(title=f"Time (in s)"))

        return fig, ""
