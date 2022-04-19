from collections import defaultdict
import statistics as stats
import datetime

import plotly.graph_objs as go
import plotly.subplots
import matrix_view.table_stats
from common import Matrix
from matrix_view import COLORS

def register():
    ComparisonPlot()

class ComparisonPlot():
    def __init__(self, ):
        self.name = f"Comparison"
        self.id_name = f"comparison"

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        try: variables.pop("inference_count")
        except KeyError: pass
        try: variables.pop("inference_fraction")
        except KeyError: pass
        try: variables.pop("training_count")
        except KeyError: pass
        try: variables.pop("training_fraction")
        except KeyError: pass
        try: variables.pop("expe")
        except KeyError: pass

        #variables.pop("partionner")

        legend_names = set()
        results = defaultdict(dict)
        group_names = []
        group_slices = dict()
        group_lengths = defaultdict(int)

        group_legends = defaultdict(list)

        slices = [1]
        ref_groups = set()
        ref_values = dict(training=None, inference=None)
        ref_keys = {}

        for entry in Matrix.all_records(params, param_lists):
            inference_part = f"{entry.params.inference_count} x inference at {int(float(entry.params.inference_fraction)*100)}%"
            training_part = f"{entry.params.training_count} x training at {int(float(entry.params.training_fraction)*100)}%"

            if params['partionner'] in ("sequential", "native"):
                group_slice = 1
            else:
                group_slice = (int(entry.params.training_count) + int(entry.params.inference_count))

            slices.append(group_slice)
            if not entry.results.training_speed:
                group_name = inference_part
            elif not entry.results.inference_speed:
                group_name = training_part
            else:
                group_name = f"{inference_part}<br>{training_part}"

            group_name += f"<br>{1/group_slice*100:.0f}% of the GPU per Pod"

            if variables:
                remaining_args = "<br>".join([f"{key}={entry.params.__dict__[key]}" for key in variables])
                group_name += "<br>" + remaining_args

            group_name = f"{group_name}"
            if params['partionner'] == "native":
                if entry.results.training_speed:
                    group_name += "<br>(training reference)"
                else:
                    group_name += "<br>(inference reference)"

            group_names.append(group_name)

            group_slices[group_name] = group_slice
            for mode_name, mode_data in dict(inference=entry.results.inference_speed, training=entry.results.training_speed).items():
                for idx, values in enumerate(mode_data.values()):
                    group_lengths[group_name] += 1

                    if mode_name == "inference":
                        legend_name = f"Inference #{idx}"
                        value = sum(values)/len(values)
                    else:
                        legend_name = f"Training #{idx}"
                        value = values

                    ref_keys[legend_name] = mode_name
                    legend_names.add(legend_name)
                    results[legend_name][group_name] = value
                    group_legends[group_name].append(legend_name)

            if params["partionner"] == "sequential":
                for key in ref_values:
                    if entry.params.__dict__[f"{key}_count"] == "1":
                        if ref_values[key] is not None: print(f"WARNING: found multiple {key} reference values (prev: {ref_values[key]}), new: {value} ...")
                        ref_values[key] = value
                        ref_groups.add(group_name)

        fig = plotly.subplots.make_subplots(specs=[[{"secondary_y": True}]])
        x_labels = []
        for legend_name in sorted(legend_names):
            x_labels = []
            x_idx = []
            y_base = []
            y_extra = []
            text_base = []
            text_extra = []

            def sort_key(group_name):
                value = 0
                if "partionner=sequential" not in group_name:
                    value += 50
                if "x inference" not in group_name:
                    value += 100
                    if "partionner=sequential" in group_name:
                        value += 50
                        #if "1 x training" in group_name: value += 50


                return f"{value:04d} {group_name}"

            group_names.sort(key=sort_key)

            width = 10/(max(map(len, group_legends.values())))

            for group_idx, group_name in enumerate(group_names):
                x_labels.append(group_name)

                group_length = group_lengths[group_name]

                try: legend_idx = group_legends[group_name].index(legend_name)
                except ValueError: legend_idx = 0


                position = group_idx*10 - (group_length/2)*width + legend_idx*width + 1/2*width

                x_idx.append(position)

                try: value = results[legend_name][group_name]
                except KeyError: value = None

                if value is None or group_name in ref_groups:
                    if group_name in ref_groups:
                        if value is not None:
                            text_base.append(f"{ref_keys[legend_name].title()} reference: {value:.0f} img/s")
                        else:
                            text_base.append(f"Reference: ?????")
                        y_base.append(value)
                    else:
                        text_base.append(None)
                        y_base.append(None)

                    text_extra.append(None)
                    y_extra.append(None)
                else:
                    slices = group_slices[group_name]
                    ref = ref_values[ref_keys[legend_name]]
                    if ref is None:
                        print(f"ERROR: no ref found for {legend_name}")
                        ref = value*group_slices[group_name]

                    local_ref = ref/slices

                    text_base.append(f"{value:.1f} img/s")
                    base = ref/group_slices[group_name]
                    extra = value-base
                    pct = (value-local_ref)/local_ref*100
                    text_extra.append(f"{pct:+.1f}%")
                    if extra >= 1:
                        y_base.append(base)
                        y_extra.append(extra)
                    else:
                        y_base.append(value)
                        y_extra.append(0.001) if abs(pct) > 0.5 else 0

            is_training = ref_keys[legend_name] == "training"
            secondary_axis = is_training
            color = "cornflowerblue" if is_training else "darkgreen"
            name = "Training" if is_training else "Inference"
            show_legend = "#0" in legend_name

            fig.add_trace(
                go.Bar(name=name, marker_color=color,
                       x=x_idx, y=y_base, text=text_base,
                       width=width-(width*0.1),
                       showlegend=show_legend,
                       legendgroup=name,
                       hoverlabel= {'namelength' :-1}),
                secondary_y=secondary_axis,
            )

            fig.add_trace(
                go.Bar(name=name, marker_color=color,
                       x=x_idx, y=y_extra, text=text_extra,
                       marker_line_color='red', marker_line_width=2,
                       width=width-(width*0.1),
                       showlegend=False,
                            hoverlabel= {'namelength' :-1}),
                secondary_y=secondary_axis,
            )

        fig.update_xaxes(
            tickvals=[10*i for i in range(len(x_labels))],
            ticktext=x_labels
        )

        if ref_keys:
            ref = ref_values[list(ref_keys.values())[0]]

            for slices in [1, 2, 3, 4, 6]:
                if ref is None: continue

                fig.add_trace(go.Scatter(
                    x=[x_idx[0]-5, x_idx[-1]],
                    y=[ref*1/slices, ref*1/slices],
                    showlegend=False,
                    mode="lines+text",
                    text=[f"100%<br>of the<br>reference<br>speed" if slices == 1 else f"{1/slices*100:.0f}%"],
                    textposition="bottom center",
                    line=dict(
                        color="gray",
                        width=1,
                        dash='dashdot',
                    ),
                ), secondary_y=True)

        yaxis_title = "<b>{what} speed</b> (in img/s, higher is better)"
        fig.update_layout(title=f"NVDIA Deep Learning SSD AI/ML Processing Speed Comparison<br>using Run:AI GPU fractional GPU", title_x=0.5,
                          showlegend=True,
                          barmode='stack',
                          yaxis_title=yaxis_title.format(what="Inference"),
                          #paper_bgcolor='rgb(248, 248, 255)',
                          plot_bgcolor='rgb(248, 248, 255)',
                          )
        fig.update_yaxes(title_text=yaxis_title.format(what="Training"), secondary_y=True)
        fig.update_yaxes(showgrid=False, showline=True, linewidth=0.1, linecolor='black')
        fig.update_xaxes(showgrid=False, showline=True, linewidth=0.1, linecolor='black', mirror=True)

        return fig, ""
