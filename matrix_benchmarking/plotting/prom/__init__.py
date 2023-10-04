import datetime
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

        cfg__check_all_thresholds = cfg.get("check_all_thresholds", False)
        cfg__show_lts = cfg.get('show_lts', False)

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
        single_expe = common.Matrix.count_records(settings, setting_lists, include_lts=cfg__show_lts) == 1
        data_threshold = []
        threshold_status = defaultdict(dict)
        threshold_passes = defaultdict(int)

        data = []
        for entry in common.Matrix.all_records(settings, setting_lists, include_lts=cfg__show_lts):
            threshold_value = entry.get_threshold(self.threshold_key)

            try: check_thresholds = entry.check_thresholds()
            except AttributeError: check_thresholds = False

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
                    y_values = [float(y)/self.y_divisor for x, y in metric.values]

                    if self.get_legend_name:
                        legend_name, legend_group = self.get_legend_name(metric_name, metric.metric)
                    else:
                        legend_name = metric.metric.get("__name__", metric_name)
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

                        if threshold_value is not None:
                            if str(threshold_value).endswith("%"):
                                _threshold_pct = int(threshold_value[:-1]) / 100
                                _threshold_value = _threshold_pct * max(y_values)
                            else:
                                _threshold_value = threshold_value

                            data.append(
                                go.Scatter(
                                    x=[x_values[0], x_values[-1]], y=[_threshold_value, _threshold_value],
                                    name=f"{legend_name} threshold",
                                    hoverlabel= {'namelength' :-1},
                                    showlegend=self.show_legend,
                                    legendgroup=legend_group,
                                    legendgrouptitle_text=legend_group,
                                    line_color="red",
                                    marker=dict(color='red', size=15, symbol="triangle-up" if self.higher_better else "triangle-down"),
                                    mode='markers+lines'))
                            entry_version = "Test"
                    else:
                        entry_version = entry.get_name(variables)
                        for y_value in y_values:
                            data.append(dict(Version=entry_version,
                                             SortIndex=sort_index,
                                             Metric=legend_name,
                                             Value=y_value))
                        if threshold_value is not None:
                            if str(threshold_value).endswith("%"):
                                _threshold_pct = int(threshold_value[:-1]) / 100
                                _threshold_value = _threshold_pct * max(y_values)
                            else:
                                _threshold_value = threshold_value

                            data_threshold.append(dict(Version=entry_version,
                                                       Value=_threshold_value,
                                                       Metric=legend_name,
                                                       SortIndex=sort_index
                                                    ))

                    if threshold_value is not None and check_thresholds:
                        if str(threshold_value).endswith("%"):
                            _threshold_pct = int(threshold_value[:-1]) / 100
                            _threshold_value = _threshold_pct * max(y_values)
                        else:
                            _threshold_value = float(threshold_value)

                        status = "PASS"
                        if self.higher_better:
                            test_passed = min(y_values) >= _threshold_value
                            if test_passed:
                                status = f"PASS: {min(y_values):.2f} >= threshold={threshold_value}"
                            else:
                                status = f"FAIL: {min(y_values):.2f} < threshold={threshold_value}"
                        else:
                            test_passed = max(y_values) <= _threshold_value
                            if test_passed:
                                status = f"PASS: {max(y_values):.2f} <= threshold={threshold_value}"
                            else:
                                status = f"FAIL: {max(y_values):.2f} > threshold={threshold_value}"

                        if test_passed:
                            threshold_passes[entry_version] += 1

                        if str(threshold_value).endswith("%"):
                            status += f" (={_threshold_value:.2f})"

                        threshold_status[entry_version][legend_group or legend_name] = status

        if not data:
            return None, "No data to plot ..."

        if single_expe:
            fig = go.Figure(data=data)

            fig.update_layout(
                title=plot_title, title_x=0.5,
                yaxis=dict(title=self.y_title, range=[0, y_max*1.05]),
                xaxis=dict(title=None if self.as_timestamp else "Time (in s)"))
        else:
            df = pd.DataFrame(data).sort_values(by=["SortIndex"])
            fig = px.box(df, x="Version", y="Value", color="Version", points="all")
            fig.update_layout(
                title=plot_title, title_x=0.5,
                yaxis=dict(title=self.y_title)
            )
            if data_threshold:
                df_threshold = pd.DataFrame(data_threshold).sort_values(by=["SortIndex"])
                fig.add_scatter(name="Threshold",
                                x=df_threshold['Version'], y=df_threshold['Value'], mode='lines+markers',
                                marker=dict(color='red', size=15, symbol="triangle-up" if self.higher_better else "triangle-down"),
                                line=dict(color='brown', width=5, dash='dot'))

        msg = []
        if threshold_status:
            msg.append(html.H3(self.title if self.title else self.name))

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
