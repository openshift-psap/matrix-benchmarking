from collections import defaultdict
import statistics as stats

import plotly.graph_objs as go
from dash import html

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
            gpu_name = entry.params.gpu_type
            gpu_name += " x "+ entry.params.gpu_count + "gpu"
            gpu_name += " x "+ entry.params.pod_count + "pods"
            exec_times = []

            def add_plot(an_entry):
                if not an_entry.results: return

                for log_filename, values in an_entry.results.thresholds.items():
                    sorted_values = sorted(values, key=lambda x:x[0])
                    thr = [xy[0] for xy in values]
                    ts = [xy[1]/1000/60 for xy in values]
                    if log_filename.startswith("/tmp"):
                        # log_filename: /tmp/ssd_MIG-GPU-d9322296-54da-ce5a-6330-3ca7707e0c5d.log
                        mig_name = " #"+log_filename.split("_")[1]

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
            xaxis=dict(title=f"Time (in min)"))
        return fig, ""

class MigThresholdOverTime():
    def __init__(self, mig_type=None):
        self.mig_type = mig_type
        self.multi_gpu = self.mig_type == "full"

        if self.multi_gpu:
            self.name = f"Multi-GPU threshold over time"
            self.mig_type = None
        elif self.mig_type:
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
            gpu_name = entry.params.gpu_type
            if self.mig_type:
                if not self.mig_type in gpu_name: continue
            else:
                if not (gpu_name == "full" or gpu_name.endswith("_1")): continue

            exec_times = []
            gpus.add(gpu_name)
            entries.append(entry)

        gpus_to_plot = defaultdict(list)
        for entry in entries:
            def add_plot(an_entry):
                nonlocal y_min, y_max
                gpu_name = gpu_full_name = an_entry.params.gpu_type
                if self.mig_type:
                    gpu_name = gpu_name.replace("_", " x ")
                else:
                    if gpu_name.endswith("_1"): gpu_name = gpu_full_name[:-2]
                    if gpu_name == "full": gpu_name = "8g.40gb (full)"

                xy = []
                for log_filename, values in an_entry.results.thresholds.items():
                    if not values: continue
                    sorted_values = sorted(values, key=lambda x:x[0])
                    thr = [xy[0] for xy in values]

                    y_min = min([y_min]+thr)
                    y_max = max([y_max]+thr)
                    ts = [xy[1]/1000/60/60 for xy in values]

                    gpus_to_plot[(gpu_name, gpu_full_name)].append([ts, thr])
            if entry.is_gathered:
                for single_entry in entry.results:
                    add_plot(single_entry)
            else:
                add_plot(entry)

        def do_complete_ts(all_thr, thr, ts):
            prev_pt = thr[0], ts[0]
            if not thr or not ts: import pdb;pdb.set_trace()
            next_pt = thr[1], ts[1]

            current_idx = 0

            complete_ts = []

            for a_thr in all_thr:
                if a_thr < thr[0]:
                    # we're before the beginning
                    complete_ts.append(None)
                    continue

                while a_thr > next_pt[0] and current_idx != len(thr):
                    # we're above the current range
                    # go to the next one

                    current_idx += 1
                    if current_idx == len(thr): break

                    prev_pt = next_pt[:]
                    next_pt = thr[current_idx], ts[current_idx]

                if current_idx == len(thr):
                    # we're above the full range
                    complete_ts.append(None)
                    continue

                # now we have the right range. Do a linear interpolation

                if a_thr == next_pt[0]:
                    a_ts = next_pt[1]
                else:
                    a_ts = prev_pt[1] + (a_thr-prev_pt[0])*(next_pt[1]-prev_pt[1])/(next_pt[0]-prev_pt[0])

                complete_ts.append(a_ts)

            return complete_ts

        for [gpu_name, gpu_full_name], xy_values in gpus_to_plot.items():
            all_thr = set()
            for ts, thr in xy_values:
                all_thr.update(thr)
            all_thr = sorted(all_thr)

            all_ts_values = defaultdict(list)

            for ts, thr in xy_values:
                all_ts = do_complete_ts(all_thr, thr, ts)

                trace = go.Scatter(x=thr, y=ts,
                               name=gpu_name + " before",
                               hoverlabel= {'namelength' :-1},
                               showlegend=True,

                               mode='lines+markers',
                               )
                #fig.add_trace(trace)
                trace = go.Scatter(x=all_thr, y=all_ts,
                               name=gpu_name + " after",
                               hoverlabel= {'namelength' :-1},
                               showlegend=True,
                               mode='lines+markers',
                               )
                #fig.add_trace(trace)

                for a_ts, a_thr in zip(all_ts, all_thr):
                    all_ts_values[a_thr].append(a_ts)

            y = []
            y_err_upper = []
            y_err_lower = []
            x = []

            for thr, ts in all_ts_values.items():
                ts_values = [t for t in ts if t is not None]
                if len(ts_values) == 1 and thr == list(all_ts_values)[-1]: continue

                x.append(thr)
                y.append(stats.mean(ts_values) if ts_values else None)
                y_err = stats.stdev(ts_values) if len(ts_values) > 2 else None
                if y[-1] is None:
                    y_err_upper.append(None)
                    y_err_lower.append(None)
                    continue
                if y_err is None: y_err = 0
                y_err_upper.append(y[-1]+y_err)
                y_err_lower.append(y[-1]-y_err)

            trace = go.Scatter(x=x, y=y,
                               name=(gpu_name + " (mean)").replace(") (", ", "),
                               hoverlabel= {'namelength' :-1},
                               line=dict(color=COLORS(sorted(gpus).index(gpu_full_name))),
                               showlegend=True,
                               legendgroup=gpu_name,
                               mode='lines',
                               )

            fig.add_trace(trace)
            showlegend_stdev = "full" not in gpu_name
            trace = go.Scatter(
                x=x+x[::-1], # x, then x reversed
                y=y_err_upper+y_err_lower[::-1], # upper, then lower reversed
                fill='toself',
                fillcolor=COLORS(sorted(gpus).index(gpu_full_name)),
                opacity=0.2,
                line=dict(color='rgba(255,255,255,0)'),
                hoverinfo="skip",
                name=(gpu_name+" (stdev)").replace(") (", ", "),
                legendgroup=gpu_name,
                showlegend=showlegend_stdev
            )
            fig.add_trace(trace)


        fig.update_layout(
            title=plot_title, title_x=0.5,
            xaxis=dict(title="Threshold", range=[y_min, y_max]),
            yaxis=dict(title=f"Time (in hr)"))
        return fig, ""

class MigTimeToThreshold():
    def __init__(self, mig_type=None, speed=False, full_gpu_isolation=False):
        self.mig_type = mig_type
        self.full_gpu_isolation = full_gpu_isolation
        self.multi_gpu = self.mig_type == "full"

        self.speed = speed
        self.name = "MIG"

        if self.multi_gpu:
            self.name = "GPU Isolation" if self.full_gpu_isolation else "Multi-GPU"

            self.mig_type = None
        elif self.mig_type:
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
        threshold = params['threshold']
        if self.multi_gpu:
            plot_title = "GPU Isolation" if self.full_gpu_isolation else "Multi-GPU"

        elif self.mig_type:
            plot_title += f" {self.mig_type} parallel execution"
        else:
            plot_title += " instances"

        plot_title += ": "
        if self.speed:
            plot_title += "Processing speed"
        else:
            plot_title += f"Time to {threshold} threshold"

        # remove unwanted entries from the `all_records` list
        entries = []
        for entry in Matrix.all_records(params, param_lists):
            gpu_name = entry.params.gpu_type
            if self.mig_type:
                if not self.mig_type in gpu_name: continue
            else:
                if not (gpu_name == "full" or gpu_name.endswith("_1")): continue

            entries.append(entry)

        plot_values = defaultdict(list)
        x_names = {}
        for entry in entries:
            def add_plot(an_entry):
                gpu_name = gpu_full_name = an_entry.params.gpu_type
                if self.mig_type:
                    gpu_name = f"{an_entry.params.gpu_type} x {an_entry.params.gpu_count}"
                else:
                    if gpu_name.endswith("_1"): gpu_name = gpu_full_name[:-2]

                    if gpu_name == "full":
                        if self.multi_gpu:
                            gpu_name = f"{an_entry.params.gpu_count} GPU" + ('s' if int(an_entry.params.gpu_count) > 1 else '')
                            if self.full_gpu_isolation:
                                gpu_name += f"x {an_entry.params.pod_count} Pods"
                        else:
                            gpu_name = "8g.40gb (full)"

                if self.multi_gpu:
                    x_value = int(an_entry.params.pod_count) if self.full_gpu_isolation \
                        else int(an_entry.params.gpu_count)

                elif self.mig_type:
                    x_value = int(gpu_name.split(" ")[-1])
                else:
                    x_value = int(gpu_name.split("g")[0])

                x_names[x_value] = gpu_name

                if not an_entry.results:
                    print("no results in", an_entry.location)
                    return

                if self.speed:
                    for mig_name, speed in an_entry.results.avg_sample_sec.items():
                        plot_values[x_value].append(speed)
                else:
                    for log_filename, values in an_entry.results.thresholds.items():
                        ts = [xy[1]/1000/60 for xy in values]
                        thr = [xy[0] for xy in values]
                        if not ts: continue
                        # should be cfg value ...
                        #if thr[-1] < 0.22: continue

                        plot_values[x_value].append(ts[-1])

            if entry.is_gathered:
                for single_entry in entry.results:
                    add_plot(single_entry)
            else:
                add_plot(entry)

        y_means = [stats.mean(y_values) for y_values in plot_values.values()]
        if not y_means:
            return go.Figure(layout=go.Layout(
        title=go.layout.Title(text="No data to plot ...")
            )), "No data to plot ..."

        if self.mig_type or self.full_gpu_isolation:
            y_mean_ref = y_means[0] #max(y_means) if self.speed else min(y_means)
        else:
            y_mean_ref = min(y_means) if self.speed else max(y_means)

        x = sorted(plot_values.keys())
        y = [stats.mean(plot_values[x_value]) for x_value in x]
        y_err = [(stats.stdev(plot_values[x_value]) if len(plot_values[x_value]) >= 2 else None) for x_value in x]

        xy_slowdown = {x_value:y_value/y_mean_ref for x_value, y_value in zip(x,y)}
        if not self.speed:
            xy_slowdown = {x_value:1/y_value for x_value, y_value in xy_slowdown.items()}

        if self.mig_type or self.full_gpu_isolation:
            x_names = [f"{x_value} instance{'s' if int(x_value) > 1 else ''}: " +
                       (f"{xy_slowdown[x_value]:.2f}x "
                        f"{'speed' if self.speed else 'slower'}" if x_value != x[0] else f"reference {'speed' if self.speed else 'time'}")
                        for x_value in x]

            x_baseline = [-100, x[-1], 100]
            y_baseline = [y_mean_ref, y_mean_ref, y_mean_ref]

            if self.speed:
                textposition = "bottom right"
            else:
                textposition = "top right"

            baseline_text = [None for _ in x_baseline]
            baseline_text[-2] = "        Reference " + ("speed" if self.speed else "time")
            baseline_textposition = "top right"
        else:
            x_names = [f"{x_names[x_value]}: " +
                       (f"{xy_slowdown[x_value]:.2f}x "
                        f"{'speed' if self.speed else 'faster'}" if x_value != x[0] else f"reference {'speed' if self.speed else 'time'}")

                       for x_value in x]
            if self.speed:
                textposition = "bottom right"
            else:
                textposition = "top right"

            x_baseline = x
            baseline_text = [None for _ in x_baseline]
            if self.speed:
                y_baseline = [y_mean_ref * x_value for x_value in x_baseline]
                #baseline_text[4] = "Perfect scaling"
                baseline_textposition = "bottom right"
            else:
                y_baseline = [y_mean_ref / x_value for x_value in x_baseline]
                baseline_text[-1] = "Perfect scaling"
                baseline_textposition = "bottom center"
        y_max = max(y_baseline + y)

        fig.add_trace(go.Scatter(x=x_baseline, y=y_baseline,
                                 mode="lines+text" + ("+markers" if not self.mig_type else ""),
                                 name="Perfect scaling",
                                 text=baseline_text,
                                 line=dict(color='royalblue', width=2, dash='dot'),
                                 textposition=baseline_textposition,
                                 ))

        fig.add_trace(go.Scatter(x=x, y=y,
                                 text=x_names,
                                 mode="lines+markers+text",
                                 textposition=textposition,
                                 error_y=dict(
                                     type='data', # value of error bar given in data coordinates
                                     array=y_err,
                                     color='black',
                                     visible=True)
                                 ))


        if self.mig_type:
            x_title = "Number of parallel executions"
        else:
            x_title = "Number of GPU execution engines"

        fig.update_layout(
            showlegend=False,
            yaxis=dict(
                title='Avg Samples / sec, higher is better' if self.speed else "Time (in min), lower is better",
                range=[0, y_max*(1.05 if self.speed else 1.1)],
            ),
            xaxis=dict(
                range=[0.9, max(x)*1.08],
                title=x_title,
            ),
            title=plot_title, title_x=0.5)

        return fig, ""
