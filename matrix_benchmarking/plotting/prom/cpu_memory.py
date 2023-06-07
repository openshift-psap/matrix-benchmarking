import datetime
import statistics as stats
from collections import defaultdict

import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
from dash import html

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

        self.skip_nodes = self.is_memory and not self.is_cluster

        table_stats.TableStats._register_stat(self)
        common.Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, settings, setting_lists, variables, cfg):
        cfg__check_all_thresholds = cfg.get("check_all_thresholds", False)
        cfg__show_lts = cfg.get("show_lts", False)

        fig = go.Figure()
        metric_names = [
            list(metric.items())[0][0] if isinstance(metric, dict) else metric
            for metric in self.metrics
        ]

        plot_title = f"Prometheus: {self.y_title}"
        y_max = 0

        y_divisor = 1024*1024*1024 if self.is_memory else 1

        single_expe = single_expe = common.Matrix.count_records(settings, setting_lists, include_lts=cfg__show_lts) == 1

        data = []
        data_rq = []
        data_lm = []
        data_threshold = []

        threshold_status = defaultdict(dict)
        threshold_passes = defaultdict(int)
        for entry in common.Matrix.all_records(settings, setting_lists, include_lts=cfg__show_lts):
            threshold_value = entry.get_threshold(self.threshold_key, None) if self.threshold_key else None

            check_thresholds = entry.check_thresholds()

            if cfg__check_all_thresholds:
                check_thresholds = True

            entry_name = entry.get_name(variables)

            sort_index = entry.get_settings()[ordered_vars[0]] if len(variables) == 1 \
                else entry_name

            for _metric in self.metrics:
                metric_name, metric_query = list(_metric.items())[0] if isinstance(_metric, dict) else (_metric, _metric)

                for metric in self.filter_metrics(entry, self.get_metrics(entry, metric_name)):
                    if not metric: continue

                    x_values = [x for x, y in metric.values]
                    y_values = [float(y)/y_divisor for x, y in metric.values]

                    metric_actual_name = metric.metric.get("__name__", metric_name)
                    legend_name = metric_actual_name
                    if metric.metric.get("container") == "POD": continue

                    if "_sum_" in metric_name:
                        legend_group = None
                        legend_name = "sum(all)"
                        if check_thresholds:
                            continue
                    else:
                        legend_group = metric.metric.get("pod", "<no podname>") + "/" + metric.metric.get("container", self.container_name) \
                            if not self.is_cluster else None

                    if self.as_timestamp:
                        x_values = [datetime.datetime.fromtimestamp(x) for x in x_values]
                    else:
                        x_start = x_values[0]
                        x_values = [x-x_start for x in x_values]

                    y_max = max([y_max]+y_values)

                    opts = {}

                    if self.skip_nodes and "node" not in metric.metric:
                        continue

                    is_req_or_lim = "limit" in legend_name or "requests" in legend_name

                    if single_expe:
                        entry_name = "Test"

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

                        data.append(
                            go.Scatter(x=x_values, y=y_values,
                                       name=legend_name,
                                       hoverlabel= {'namelength' :-1},
                                       showlegend=True,
                                       legendgroup=legend_group,
                                       legendgrouptitle_text=legend_group,
                                       **opts))

                        if not is_req_or_lim and check_thresholds:
                            data.append(
                                go.Scatter(x=[x_values[0], x_values[-1]], y=[threshold_value, threshold_value],
                                           name="threshold",
                                           hoverlabel= {'namelength' :-1},
                                           showlegend=True,
                                           line_color="red",
                                           marker=dict(color='red', size=15, symbol="triangle-down"),
                                           legendgroup=legend_group,
                                           legendgrouptitle_text=legend_group))

                    else:
                        if threshold_value:
                            data_threshold.append(dict(Version=entry_name,
                                                       SortIndex=sort_index,
                                                       Value=threshold_value,
                                                       Metric=legend_name))

                        if is_req_or_lim:
                            lst = data_lm if "limits" in legend_name else data_rq

                            lst.append(dict(Version=entry_name,
                                            SortIndex=sort_index,
                                            Value=y_values[0],
                                            Metric=legend_name))

                        else:
                            for y_value in y_values:
                                data.append(dict(Version=entry_name,
                                                 SortIndex=sort_index,
                                                 Metric=legend_name,
                                                 Value=y_value))


                    if not is_req_or_lim and threshold_value and check_thresholds:
                        if max(y_values) > float(threshold_value):
                            status = f"FAIL: {max(y_values):.2f} > threshold={threshold_value}"
                        else:
                            status = f"PASS: {max(y_values):.2f} <= threshold={threshold_value}"
                            threshold_passes[entry_name] += 1

                        threshold_status[entry_name][legend_group] = status

        if not data:
            return None, "No data to plot ..."

        if single_expe:
            fig = go.Figure(data=data)

            fig.update_layout(
                title=plot_title, title_x=0.5,
                yaxis=dict(title=self.y_title + (" (in Gi)" if self.is_memory else ""), range=[0, y_max*1.05]),
                xaxis=dict(title=f"Time (in s)"))
        else:
            df = pd.DataFrame(data).sort_values(by=["SortIndex"])

            fig = px.box(df, x="Version", y="Value", color="Version")
            fig.update_layout(
                title=plot_title, title_x=0.5,
                yaxis=dict(title=self.y_title + (" (in Gi)" if self.is_memory else ""))
            )
            if data_rq:
                df_rq = pd.DataFrame(data_rq).sort_values(by=["SortIndex"])
                fig.add_scatter(name="Request",
                                x=df_rq['Version'], y=df_rq['Value'], mode='lines',
                                line=dict(color='orange', width=5, dash='dot'))
            if data_lm:
                df_lm = pd.DataFrame(data_lm).sort_values(by=["SortIndex"])
                fig.add_scatter(name="Limit",
                                x=df_lm['Version'], y=df_lm['Value'], mode='lines',
                                line=dict(color='red', width=5, dash='dot'))
            if data_threshold:
                df_threshold = pd.DataFrame(data_threshold).sort_values(by=["SortIndex"])
                fig.add_scatter(name="Threshold",
                                x=df_threshold['Version'], y=df_threshold['Value'], mode='lines+markers',
                                marker=dict(color='red', size=15, symbol="triangle-down"),
                                line=dict(color='brown', width=5, dash='dot'))

        msg = []
        if threshold_status:
            msg.append(html.H3(self.y_title))

        for entry_name, status in threshold_status.items():
            total_count = len(status)
            pass_count = threshold_passes[entry_name]
            success = pass_count == total_count

            msg += [html.B(entry_name), ": ", html.B("PASSED" if success else "FAILED"), f" ({pass_count}/{total_count} success{'es' if pass_count > 1 else ''})"]
            details = []
            for legend_name, entry_status in status.items():
                entry_details = html.Ul(html.Li(entry_status))
                details.append(html.Li([legend_name, entry_details]))

            msg.append(html.Ul(details))

        return fig, msg
