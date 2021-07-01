from collections import defaultdict
import statistics as stats

import plotly.graph_objs as go

import matrix_view.table_stats
import matrix_view
from common import Matrix
from matrix_view import COLORS
from matrix_view import COLORS

# https://plotly.com/python/marker-style/#custom-marker-symbols
SYMBOLS = [
    "circle",
    "cross",
    "triangle-down",
    "x",
    "diamond",
    "hexagram",
]

class Plot():
    def __init__(self):
        self.name = "Time to threshold"
        self.id_name = self.name.lower().replace(" ", "_")

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()

        plot_title = f"Time to threshold: (lower is better)"
        y_max = 0

        gpus = defaultdict(dict)
        for entry in Matrix.all_records(params, param_lists):
            threshold = float(entry.params.threshold)
            gpu_name = entry.params.gpu

            exec_times = []

            def add_plot(an_entry):
                for log_filename, values in an_entry.results.thresholds.items():
                    sorted_values = sorted(values, key=lambda x:x[0])
                    thr = [xy[0] for xy in values]
                    ts = [xy[1]/1000/60/60 for xy in values]
                    if log_filename.startswith("/tmp"):
                        # log_filename: /tmp/ssd_MIG-GPU-d9322296-54da-ce5a-6330-3ca7707e0c5d_5_0.log
                        mig_name = " #"+log_filename.split("_")[2]
                    else:
                        mig_name = ""

                    trace = go.Scatter(x=ts, y=thr,
                                       name=f"{gpu_name}{mig_name}",
                                       hoverlabel= {'namelength' :-1},
                                       showlegend=True,
                                       mode='markers+lines')
                    fig.add_trace(trace)

            if entry.is_gathered:
                for single_entry in entry.results:
                    add_plot(single_entry)
            else:
                add_plot(entry)

        fig.update_layout(
            title=plot_title, title_x=0.5,
            yaxis=dict(title="Threshold", range=[0, y_max*1.05]),
            xaxis=dict(title=f"Time (in hr)"))
        return fig, ""

class MigThresholdOverTime():
    def __init__(self, mig_type=None):
        self.mig_type = mig_type
        if self.mig_type:
            self.name = f"MIG {self.mig_type} threshold over time"
        else:
            self.name = "MIG threshold over time"

        self.id_name = self.name.lower().replace(" ", "_")

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()
        if self.mig_type:
            plot_title = f"MIG {self.mig_type} threshold over the time, parallel execution (lower is better)"
        else:
            plot_title = f"MIG instance comparison: Threshold over the time (lower is better)"
        y_max = 0
        y_min = 1

        gpus = set()
        entries = []
        for entry in Matrix.all_records(params, param_lists):
            threshold = float(entry.params.threshold)
            gpu_name = entry.params.gpu
            if self.mig_type:
                if not self.mig_type in gpu_name: continue
            else:
                if not (gpu_name == "full" or gpu_name.endswith("_1")): continue

            exec_times = []
            gpus.add(gpu_name)
            entries.append(entry)

        gpus_plotted = []
        for entry in entries:
            def add_plot(an_entry):
                nonlocal y_min, y_max
                gpu_name = gpu_full_name = an_entry.params.gpu
                if self.mig_type:
                    gpu_name = gpu_name.replace("_", " x ")
                else:
                    if gpu_name.endswith("_1"): gpu_name = gpu_full_name[:-2]
                    if gpu_name == "full": gpu_name = "8g.40gb (full)"

                for log_filename, values in an_entry.results.thresholds.items():
                    sorted_values = sorted(values, key=lambda x:x[0])
                    thr = [xy[0] for xy in values]

                    y_min = min([y_min]+thr)
                    y_max = max([y_max]+thr)
                    ts = [xy[1]/1000/60/60 for xy in values]
                    showlegend = gpu_name not in gpus_plotted
                    gpus_plotted.append(gpu_name)
                    trace = go.Scatter(x=thr, y=ts,
                                       name=gpu_name,
                                       hoverlabel= {'namelength' :-1},
                                       line=dict(color=COLORS(sorted(gpus).index(gpu_full_name))),
                                       showlegend=showlegend,
                                       legendgroup=gpu_name,
                                       mode='markers+lines')
                    fig.add_trace(trace)

            if entry.is_gathered:
                for single_entry in entry.results:
                    add_plot(single_entry)
            else:
                add_plot(entry)

        fig.update_layout(
            title=plot_title, title_x=0.5,
            xaxis=dict(title="Threshold", range=[y_min, y_max]),
            yaxis=dict(title=f"Time (in hr)"))
        return fig, ""

class MigTimeToThreshold():
    def __init__(self, mig_type=None, speed=False):
        self.mig_type = mig_type
        self.speed = speed
        self.name = "MIG"

        if self.mig_type:
            self.name += f" {self.mig_type}"
        else:
            self.name += " instances"
        if self.speed:
            self.name += " processing speed"
        else:
            self.name += " time to threshold"

        self.id_name = self.name.lower().replace(" ", "_")

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()
        plot_title = "MIG"
        if self.mig_type:
            plot_title += f" {self.mig_type} parallel execution"
        else:
            plot_title += " instances"
        plot_title += ": "
        if self.speed:
            plot_title += "Processing speed (higher is better)"
        else:
            plot_title += "Time to 0.23 threshold (lower is better)"

        entries = []
        for entry in Matrix.all_records(params, param_lists):
            threshold = float(entry.params.threshold)
            gpu_name = entry.params.gpu
            if self.mig_type:
                if not self.mig_type in gpu_name: continue
            else:
                if not (gpu_name == "full" or gpu_name.endswith("_1")): continue

            exec_times = []

            entries.append(entry)

        plot_values = defaultdict(list)
        for entry in entries:
            def add_plot(an_entry):
                gpu_name = gpu_full_name = an_entry.params.gpu
                if self.mig_type:
                    gpu_name = gpu_name.replace("_", " x ")
                else:
                    if gpu_name.endswith("_1"): gpu_name = gpu_full_name[:-2]
                    if gpu_name == "full": gpu_name = "8g.40gb (full)"

                if self.speed:
                    for mig_name, speed in an_entry.results.avg_sample_sec.items():
                        plot_values[gpu_name].append(speed)
                else:
                    for log_filename, values in an_entry.results.thresholds.items():
                        ts = [xy[1]/1000/60/60 for xy in values]
                        thr = [xy[0] for xy in values]
                        if not ts: continue
                        if thr[-1] < 0.22: continue
                        plot_values[gpu_name].append(ts[-1])

            if entry.is_gathered:
                for single_entry in entry.results:
                    add_plot(single_entry)
            else:
                add_plot(entry)

        y_means = [stats.mean(y_values) for y_values in plot_values.values()]
        y_mean_ref = max(y_means) if self.speed else min(y_means)
        y_max = 0

        idx = 0
        for gpu_name, y_values in plot_values.items():
            x = [None for _ in range(len(plot_values))]
            y = [None for _ in range(len(plot_values))]
            y_err = [None for _ in range(len(plot_values))]
            y_relative = [None for _ in range(len(plot_values))]
            if gpu_name == "full": gpu_name = "8g.40gb (full)"
            y_max = max([y_max] + y_values)
            x[idx] = gpu_name
            y[idx] = stats.mean(y_values)
            y_err[idx] = stats.stdev(y_values) \
              if len(y_values) > 2 else None

            if self.speed:
                y_relative[idx] = f"{int(y[idx]/y_mean_ref*100)}%"
            else:
                y_relative[idx] = f"{y[idx]/y_mean_ref:.2f}x"
            y_relative[idx] += " "*12 # push outside of error bar

            fig.add_trace(go.Bar(x=x, y=y,
                                 text=y_relative,
                                 textposition='outside',
                                 name=gpu_name,
                                 marker_color=COLORS(idx),
                                 error_y=dict(
                                     type='data', # value of error bar given in data coordinates
                                     array=y_err,

                                     visible=True)))
            idx += 1
        fig.update_layout(
            showlegend=False,
            yaxis=dict(
                title='Avg Samples / sec' if self.speed else "Time (in hr)",
                range=[0, y_max*(1.10 if self.speed else 1.1)],
                #titlefont_size=16,
                #tickfont_size=14,
            ),
            barmode='stack',
            title=plot_title, title_x=0.5)
        return fig, ""
