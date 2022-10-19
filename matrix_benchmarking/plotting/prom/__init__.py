import datetime

import plotly.graph_objs as go
import plotly.express as px
import pandas as pd

import matrix_benchmarking.plotting.table_stats as table_stats
import matrix_benchmarking.common as common


def default_get_metrics(entry, metric):
    return entry.results.metrics[metric]


class Plot():
    def __init__(self, metrics, name, title, y_title,
                 get_metrics=default_get_metrics,
                 filter_metrics=lambda entry, metrics: metrics,
                 as_timestamp=False,
                 get_legend_name=None,
                 show_metrics_in_title=False,
                 show_queries_in_title=False,
                 show_legend=True,
                 y_divisor=1,
                 higher_better=False,
                 ):
        self.name = name
        self.id_name = f"prom_overview_{''.join( c for c in self.name if c not in '?:!/;()' ).replace(' ', '_').lower()}"
        self.title = title
        self.metrics = metrics
        self.y_title = y_title
        self.y_divisor = y_divisor
        self.filter_metrics = filter_metrics
        self.get_metrics = get_metrics
        self.as_timestamp = as_timestamp
        self.get_legend_name = get_legend_name
        self.show_metrics_in_title = show_metrics_in_title
        self.show_queries_in_title = show_queries_in_title
        self.show_legend = show_legend
        self.threshold_key = self.id_name
        self.higher_better = higher_better

        table_stats.TableStats._register_stat(self)
        common.Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, settings, setting_lists, variables, cfg):
        plot_title = self.title if self.title else self.name

        if self.show_metrics_in_title:
            metric_names = [
                list(metric.items())[0][0] if isinstance(metric, dict) else metric
                for metric in self.metrics.keys()
            ]
            plot_title += f"<br>{'<br>'.join(metric_names)}"

        if self.show_queries_in_title:
            queries_names = self.metrics.values()
            plot_title += f"<br>{'<br>'.join(queries_names)}"

        y_max = 0

        single_expe = sum(1 for _ in common.Matrix.all_records(settings, setting_lists)) == 1
        data_threshold = []

        data = []
        for entry in common.Matrix.all_records(settings, setting_lists):
            threshold_value = entry.results.thresholds.get(self.threshold_key) if self.threshold_key else None

            for metric in self.metrics:
                metric_name, metric_query = list(metric.items())[0] if isinstance(metric, dict) else (metric, metric)

                for metric in self.filter_metrics(entry, self.get_metrics(entry, metric_name)):
                    if not metric: continue

                    x_values = [x for x, y in metric["values"]]
                    y_values = [float(y)/self.y_divisor for x, y in metric["values"]]

                    if self.get_legend_name:
                        legend_name, legend_group = self.get_legend_name(metric_name, metric["metric"])
                    else:
                        legend_name = metric["metric"].get("__name__", metric_name)
                        legend_group = None

                    if legend_group: legend_group = str(legend_group)
                    else: legend_group = None

                    if self.as_timestamp:
                        x_values = [datetime.datetime.fromtimestamp(x) for x in x_values]
                    else:
                        x_start = x_values[0]
                        x_values = [x-x_start for x in x_values]

                    y_max = max([y_max]+y_values)
                    if single_expe:
                        data.append(
                            go.Scatter(
                                x=x_values, y=y_values,
                                name=str(legend_name),
                                hoverlabel= {'namelength' :-1},
                                showlegend=self.show_legend,
                                legendgroup=legend_group,
                                legendgrouptitle_text=legend_group,
                                mode='markers+lines'))
                    else:
                        for y_value in y_values:
                            data.append(dict(Version=entry.location.name,
                                             Metric=legend_name,
                                             Value=y_value))
                        if threshold_value:
                            if threshold_value.endswith("%"):
                                _threshold_pct = int(threshold_value[:-1]) / 100
                                _threshold_value = _threshold_pct * max(y_values)
                            else:
                                _threshold_value = threshold_value

                            data_threshold.append(dict(Version=entry.location.name,
                                                       Value=_threshold_value,
                                                       Metric=legend_name))

        if single_expe:
            fig = go.Figure(data=data)

            fig.update_layout(
                title=plot_title, title_x=0.5,
                yaxis=dict(title=self.y_title, range=[0, y_max*1.05]),
                xaxis=dict(title=None if self.as_timestamp else "Time (in s)"))
        else:
            df = pd.DataFrame(data).sort_values(by=["Version"])
            fig = px.box(df, x="Version", y="Value", color="Version")
            fig.update_layout(
                title=plot_title, title_x=0.5,
                yaxis=dict(title=self.y_title)
            )
            if data_threshold:
                df_threshold = pd.DataFrame(data_threshold).sort_values(by=["Version"])
                fig.add_scatter(name="Threshold",
                                x=df_threshold['Version'], y=df_threshold['Value'], mode='lines+markers',
                                marker=dict(color='red', size=15, symbol="triangle-up" if self.higher_better else "triangle-down"),
                                line=dict(color='brown', width=5, dash='dot'))
        return fig, ""
