import datetime

import plotly.graph_objs as go
import plotly.express as px
import pandas as pd

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
        self.threshold_key = f"{y_title.replace(' ', '_').replace(':', '').lower()}"

        table_stats.TableStats._register_stat(self)
        common.Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, settings, setting_lists, variables, cfg):
        fig = go.Figure()
        metric_names = [
            list(metric.items())[0][0] if isinstance(metric, dict) else metric
            for metric in self.metrics
        ]

        plot_title = f"Prometheus: {self.y_title}"
        y_max = 0

        y_divisor = 1024*1024*1024 if self.is_memory else 1

        single_expe = sum(1 for _ in common.Matrix.all_records(settings, setting_lists)) == 1

        data = []
        data_rq = []
        data_lm = []
        data_threshold = []
        for entry in common.Matrix.all_records(settings, setting_lists):
            try: threshold_value = entry.results.thresholds.get(self.threshold_key) if self.threshold_key else None
            except AttributeError: threshold_value = None

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

                    if single_expe:
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
                        data.append(trace)
                    else:
                        if threshold_value:
                            data_threshold.append(dict(Version=entry.location.name,
                                                       Value=threshold_value,
                                                       Metric=legend_name))
                        if "limit" in legend_name or "requests" in legend_name:
                            lst = data_lm if "limits" in legend_name else data_rq

                            lst.append(dict(Version=entry.location.name,
                                            Value=y_values[0],
                                            Metric=legend_name))
                        else:
                            for y_value in y_values:
                                data.append(dict(Version=entry.location.name,
                                                 Metric=legend_name,
                                                 Value=y_value))


        if single_expe:
            fig = go.Figure(data=data)

            fig.update_layout(
                title=plot_title, title_x=0.5,
                yaxis=dict(title=self.y_title + (" (in Gi)" if self.is_memory else ""), range=[0, y_max*1.05]),
                xaxis=dict(title=f"Time (in s)"))
        else:
            df = pd.DataFrame(data).sort_values(by=["Version"])
            fig = px.box(df, x="Version", y="Value", color="Version")
            fig.update_layout(
                title=plot_title, title_x=0.5,
                yaxis=dict(title=self.y_title + (" (in Gi)" if self.is_memory else ""))
            )
            if data_rq:
                df_rq = pd.DataFrame(data_rq).sort_values(by=["Version"])
                fig.add_scatter(name="Request",
                                x=df_rq['Version'], y=df_rq['Value'], mode='lines',
                                line=dict(color='orange', width=5, dash='dot'))
            if data_lm:
                df_lm = pd.DataFrame(data_lm).sort_values(by=["Version"])
                fig.add_scatter(name="Limit",
                                x=df_lm['Version'], y=df_lm['Value'], mode='lines',
                                line=dict(color='red', width=5, dash='dot'))
            if data_threshold:
                df_threshold = pd.DataFrame(data_threshold).sort_values(by=["Version"])
                fig.add_scatter(name="Threshold",
                                x=df_threshold['Version'], y=df_threshold['Value'], mode='lines+markers',
                                marker=dict(color='red', size=15, symbol="triangle-down"),
                                line=dict(color='brown', width=5, dash='dot'))
        return fig, ""
