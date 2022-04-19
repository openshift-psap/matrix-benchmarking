from collections import defaultdict
import statistics as stats
import datetime

import plotly.graph_objs as go

import matrix_benchmarking.plotting.table_stats as table_stats
import matrix_benchmarking.common as common
import matrix_benchmarking.plotting.ui as ui
import matrix_benchmarking.plotting.prom as prom


def register():
    training_time = lambda results: results.training_time / 60 if results.training_time is not None else None

    Plot("Throughput",
         None,
         lambda results: results.throughput,
         "Average Throughput (in sentences/sec, higher is better)")
    Plot("Throughput with overhead",
         None,
         lambda results: results.throughput_with_overhead,
         "Average Throughput (in sentences/sec, higher is better)")
    Plot("Training time",
         "Total Training Time",
         training_time,
         "Total Training Time (in minutes, lower is better)")

    Plot("GPU Power Usage",
         None,
         lambda results: results.gpu_power_usage,
         "Sum of the average power consumption (in Watt, lower is better)")
    Plot("GPU Compute Usage",
         None,
         lambda results: results.gpu_compute_usage,
         "Sum of the average compute usage (in %, lower is better)")
    Plot("GPU Memory Usage",
         None,
         lambda results: results.gpu_compute_usage,
         "Sum of the average memory usage (in MB, lower is better)")
    Plot("CPU Usage",
         None,
         lambda results: results.cpu_usage,
         "Sum of the average CPU usage (in CPU count, lower is better)")
    Plot("Network Transmit Usage",
         None,
         lambda results: results.network_usage,
         "Sum of the network transmit usage (in bytes, lower is better)")

    prom.Plot("DCGM_FI_DEV_POWER_USAGE", "Power usage")
    prom.Plot("DCGM_FI_DEV_FB_USED", "Memory usage")
    prom.Plot("DCGM_FI_DEV_GPU_UTIL", "Compute usage")


class Plot():
    def __init__(self, name, title, y_key, y_title):
        self.name = name
        self.id_name = name
        self.title = title if title else name
        self.y_key = y_key
        self.y_title = y_title

        table_stats.TableStats._register_stat(self)
        common.Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()

        XY = defaultdict(dict)
        XYerr_pos = defaultdict(dict)
        XYerr_neg = defaultdict(dict)

        x_key = lambda entry: int(entry.params.num_gpu)

        try: variables.pop("num_gpu")
        except: KeyError: ...

        is_gathered = False
        for entry in common.Matrix.all_records(params, param_lists):
            legend_name = " ".join([f"{key}={entry.params.__dict__[key]}" for key in variables])

            if entry.is_gathered:
                is_gathered = True

                y_values = [self.y_key(entry.results) for entry in entry.results]

                y = stats.mean(y_values)
                y_err = stats.stdev(y_values) if len(y_values) > 2 else 0

                legend_name += " " + " ".join(entry.gathered_keys.keys()) + f" x{len(entry.results)}"

                if self.name == "Date":
                    XYerr_pos[legend_name][x_key(entry)] = y_err
                    XYerr_neg[legend_name][x_key(entry)] = y_err
                else:
                    XYerr_pos[legend_name][x_key(entry)] = y + y_err
                    XYerr_neg[legend_name][x_key(entry)] = y - y_err
            else:
                y = self.y_key(entry.results)

            XY[legend_name][x_key(entry)] = y

        y_max = 0

        data = []
        for legend_name in XY:
            x = list(sorted(XY[legend_name].keys()))
            y = list([XY[legend_name][_x] for _x in x])

            y_max = max([_y for _y in y if _y is not None] + [y_max])

            color = ui.COLORS(list(XY.keys()).index(legend_name))

            data.append(go.Scatter(name=legend_name,
                                   x=x, y=y,
                                   mode="markers+lines",
                                   line=dict(color=color, width=1),
                                   hoverlabel= {'namelength' :-1},
                                   legendgroup=legend_name,
                                   ))

            if not XYerr_pos: continue

            y_err_pos = list([XYerr_pos[legend_name][_x] for _x in x])
            y_err_neg = list([XYerr_neg[legend_name][_x] for _x in x])

            data.append(go.Scatter(name=legend_name,
                                   x=x, y=y_err_pos,
                                   line=dict(color=color, width=0),
                                   mode="lines",
                                   showlegend=False,
                                   legendgroup=legend_name,
                                   ))
            data.append(go.Scatter(name=legend_name,
                                   x=x, y=y_err_neg,
                                   showlegend=False,
                                   mode="lines",
                                   fill='tonexty',
                                   line=dict(color=color, width=0),
                                   legendgroup=legend_name,
                                   ))




        fig = go.Figure(data=data)
        log_scale = cfg.get("log-scale", False) == "y"

        if log_scale:
            fig.update_xaxes(type="log")
            fig.update_yaxes(type="log")
            import math
            # https://plotly.com/python/reference/layout/yaxis/#layout-yaxis-range
            y_max = math.log(y_max, 10)


        fig.update_layout(
            title=self.title, title_x=0.5,
            showlegend=True,
            xaxis_title="Number of GPUs" + (" [log scale]" if log_scale else ""),
            yaxis_title=self.y_title + (" [log scale]" if log_scale else ""),
        )



        return fig, ""
