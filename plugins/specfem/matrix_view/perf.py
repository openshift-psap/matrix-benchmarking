import statistics as stats

import plotly.graph_objs as go

from ui.table_stats import TableStats
from ui import matrix_view
from collections import defaultdict

from ui.matrix_view import COLORS

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
    def __init__(self, mode):
        if mode not in ("time", "time_comparison", "speedup", "efficiency"):
            raise KeyError(f"Invalid key: {mode}")

        self.mode = mode
        self.name = mode.title().replace("_", " ")
        self.id_name = mode
        TableStats._register_stat(self)


    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()

        table_def = None
        table = "worker.timing"
        field = "total_time"
        plot_title = f"Specfem {self.name}"

        RESERVED_VARIABLES = ("machines", "mpi-slots")

        if "nex" not in variables and "nex" in params:
            plot_title += f" for {params['nex']}nex"

        if self.mode == "time_comparison":
            ref_var = None
        main_var = None
        second_var = None
        third_var = None
        for var in ordered_vars:
            if var in RESERVED_VARIABLES: continue
            if main_var is None:
                main_var = var
                if self.mode == "time_comparison":
                    ref_var = var
            elif second_var is None:
                second_var = var
            else:
                third_var = var
                break
        else:
            if main_var is None:
                return None, "Error, not enough variables selected ..."

        for var in ordered_vars:
            if var in RESERVED_VARIABLES + (main_var, ): continue
            if var.startswith("@") and var != ordered_vars[-1]:
                rolling_var = var
                if rolling_var == second_var:
                    second_var = third_var
                break
        else:
            rolling_var = None

        index_for_colors = set()
        index_for_symbols = set()

        results = defaultdict(list)
        if rolling_var is not None:
            all_rolling_results = defaultdict(lambda:defaultdict(list))
        main_var_value = {}
        second_var_value = {}
        line_symbol = {}
        line_color = {}

        if self.mode == "time_comparison":
            ref_keys = {}
            for ref_var in ordered_vars:
                if ref_var in RESERVED_VARIABLES + (rolling_var, ): continue
                break # ref_var set to the first (main) variable
            ref_var = cfg.get('perf.cmp.ref_var', ref_var)
            ref_value = cfg.get('perf.cmp.ref_value', None)
            if ref_value is None:
                ref_value = str(variables.get(ref_var, ["<invalid ref_key>"])[0])
            plot_title += f". Reference: <b>{ref_var}={ref_value}</b>"

        plot_title += f" (colored by <b>{main_var}</b>"
        if second_var:
            plot_title += f", symbols by <b>{second_var}</b>)"
        plot_title += ")"

        for entry in matrix_view.all_records(params, param_lists):
            if table_def is None:
                for table_key in entry.tables:
                    if not table_key.startswith(f"#{table}|"): continue
                    table_def = table_key
                    break
                else:
                    return {'layout': {'title': f"Error: no table named '{table_key}'"}}

            time = entry.tables[table_def][1][0][0]
            entry.params.time = time

            ref_key = ""
            legend_name = ""
            for var in ordered_vars:
                if var in RESERVED_VARIABLES + (rolling_var, ): continue
                legend_name += f" {var}={params[var]}"

                if self.mode == "time_comparison":
                    ref_key += f" {var}=" + str((params[var] if var != ref_var else ref_value))

            legend_name = legend_name.strip()

            if self.mode == "time_comparison":
                ref_keys[legend_name] = ref_key.strip()

            main_var_value[legend_name] = entry.params.__dict__[main_var]
            second_var_value[legend_name] = entry.params.__dict__.get(second_var, None)

            if rolling_var is None:
                results[legend_name].append(entry.params)
            else:
                rolling_val = entry.params.__dict__[rolling_var]
                all_rolling_results[legend_name][f"machines={entry.params.machines}"].append(entry.params)

            index_for_colors.add(main_var_value[legend_name])
            index_for_symbols.add(second_var_value[legend_name])
            line_color[legend_name] = lambda: COLORS(sorted(index_for_colors).index(entry_params.__dict__[main_var]))
            line_symbol[legend_name] = lambda: SYMBOLS[sorted(index_for_symbols).index(entry_params.__dict__[second_var])]

        x_max = 0
        y_max = 0
        y_min = 0
        def sort_key(legend_name):
            first_kv, _, other_kv = legend_name.partition(" ")
            if self.mode == "time_comparison":
                first_kv, _, other_kv = other_kv.partition(" ")
            k, v = first_kv.split("=")
            try: new_v = "{:20}".format(int(v))
            except Exception: new_v = v
            return f"{new_v} {other_kv}"

        if rolling_var is not None:
            for legend_name, rolling_results in all_rolling_results.items():
                for machine_count, entries_params in rolling_results.items():
                    times = []
                    for entry_params in entries_params:
                        times.append(entry_params.time)
                    # shallow copy of the last entry_params
                    entry_params_cpy = entry_params.__class__(**entry_params.__dict__)
                    entry_params_cpy.time = stats.mean(times)
                    entry_params_cpy.time_stdev = stats.stdev(times)
                    results[legend_name].append(entry_params_cpy)

        if self.mode == "time_comparison":
            ref_values = {}

            for ref_key in set(ref_keys.values()):
                if ref_key not in results:
                    print("MISSING", ref_key)
                    continue
                for entry_params in results[ref_key]:
                    if ref_key in ref_values: continue
                    ref_values[ref_key + f" && machines={entry_params.machines}"] = entry_params.time

        for legend_name in sorted(results.keys(), key=sort_key):
            x = []
            y = []
            if rolling_var is not None:
                err = []

            if self.mode in ("speedup", "efficiency"):
                ref_machine_time = [100, 0]
                for entry_params in results[legend_name]:
                    if int(entry_params.machines) < ref_machine_time[0]:
                        ref_machine_time = [int(entry_params.machines), entry_params.time]

                ref_time = ref_machine_time[1]/ref_machine_time[0]

            for entry_params in results[legend_name]:
                if self.mode == "time":
                    y_val = entry_params.time
                    if rolling_var is not None:
                        err.append(entry_params.time_stdev)
                elif self.mode == "speedup":
                    y_val = entry_params.time/ref_time
                elif self.mode == "efficiency":
                    y_val = entry_params.time/ref_time/int(entry_params.machines)
                elif self.mode == "time_comparison":
                    ref_values_key = ref_keys[legend_name] + f" && machines={entry_params.machines}"
                    try:
                        time_ref_value = ref_values[ref_values_key]
                    except KeyError:
                        y_val = None
                        #print("missing:", ref_values_key, ref_values.keys())
                    else:
                        time = entry_params.time
                        y_val = (time_ref_value-time)/time_ref_value * 100
                else:
                    raise RuntimeError(f"Invalid mode: {self.mode}")
                if y_val is None: continue
                x.append(int(entry_params.machines))
                y.append(y_val)

            x_max = max([x_max] + x)
            y_max = max([y_max] + [_y for _y in y if _y is not None])
            y_min = min([y_min] + [_y for _y in y if _y is not None])

            name = legend_name
            if self.mode == "time_comparison":
                if legend_name in ref_keys.values():
                    #name += " (reference)"

                    trace = go.Scatter(x=x, y=y,
                                       name=name,
                                       legendgroup=main_var_value[legend_name],
                                       hoverlabel= {'namelength' :-1},
                                       showlegend=False,
                                       mode='markers+lines',
                                       line=dict(color="black"))
                    fig.add_trace(trace)
                    continue
                else:
                    # do not plot if no reference data available at all
                    if not [_y for _y in y if _y is not None]: continue

            color = line_color[legend_name]()

            try:
                symbol = line_symbol[legend_name]()
            except Exception:
                marker = dict(symbol="circle-dot")
            else:
                marker = dict(symbol=symbol,
                              size=8, line_width=2,
                              line_color="black", color=color)

            trace = go.Scatter(x=x, y=y,
                               name=name,
                               legendgroup=main_var_value[legend_name],
                               hoverlabel= {'namelength' :-1},
                               mode='markers+lines',
                               line=dict(color=color),
                               marker=marker)
            fig.add_trace(trace)
            if rolling_var is not None:
                trace = go.Scatter(x=x, y=[_y - _err for _y, _err in zip(y, err)],
                                   name=name,
                                   legendgroup=main_var_value[legend_name],
                                   hoverlabel= {'namelength' :-1},
                                   showlegend=False, mode="lines",
                                   line=dict(color=color))

                fig.add_trace(trace)
                trace = go.Scatter(x=x, y=[_y + _err for _y, _err in zip(y, err)],
                                   name=name,
                                   legendgroup=main_var_value[legend_name],
                                   hoverlabel= {'namelength' :-1},
                                   mode="lines",
                                   fill='tonexty', showlegend=False,
                                   line=dict(color=color))
                fig.add_trace(trace)

        if self.mode == "time":
            y_title = "Execution time (in s)"
            y_min = 0
        elif self.mode == "speedup":
            y_title = "Speedup factor"
        elif self.mode == "efficiency":
            y_title = "Efficiency"
        elif self.mode == "time_comparison":
            y_title = "Slowdown comparison (in %)"
            if y_max == 0: y_max = 1

        fig.update_layout(
            title=plot_title,
            yaxis=dict(title=y_title, range=[y_min*1.01, y_max*1.01]),
            xaxis=dict(title="Number of machines", range=[0, x_max+1]))


        return fig, ""
