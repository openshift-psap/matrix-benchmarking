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
    def __init__(self, mode, what):
        if what not in ("time", "time_comparison", "speedup", "efficiency", "strong_scaling"):
            raise KeyError(f"Invalid key: {mode}")

        self.mode = mode
        self.what = what
        self.name = what.title().replace("_", " ")
        self.id_name = what
        TableStats._register_stat(self)


    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()

        table_def = None
        table = "worker.timing"
        field = "timing.total_time"

        cfg__invert_time = cfg.get('perf.invert_time', False)
        cfg__no_avg = cfg.get('perf.no_avg', False)
        cfg__legend_pos = cfg.get('perf.legend_pos', False)
        cfg__include_only = cfg.get('perf.include_only', "")

        try:
            cfg__x_var = cfg['perf.x_var']
            print(f"INFO: using {cfg__x_var} as X variable")
        except KeyError:
            cfg__x_var = "machines"

        if cfg__include_only:
            cfg__include_only = cfg__include_only.split(",")
            print(f"INFO: Include only '{', '.join(cfg__include_only)}' platforms.")

        plot_title = f"{self.mode.title()}"

        if cfg__invert_time and self.what == "time":
            plot_title += f" Simulation Speed"
        else:
            if self.mode == "gromacs":
                plot_title += " Simulation"
            plot_title += f" {self.name}"

        RESERVED_VARIABLES = (cfg__x_var, "mpi-slots")

        if "nex" not in variables and "nex" in params:
            plot_title += f" for {params['nex']}nex"

        if self.what in ("time_comparison", "strong_scaling"):
            ref_var = None

        main_var = None
        second_var = None
        third_var = None
        for var in ordered_vars:
            if var in RESERVED_VARIABLES: continue
            if main_var is None:
                main_var = var
                if self.what in ("time_comparison", "strong_scaling"):
                    ref_var = var
            elif second_var is None:
                second_var = var
            else:
                third_var = var
                break
        else:
            if main_var is None:
                return None, "Error, not enough variables selected ..."

        for var in ordered_vars if not cfg__no_avg else []:
            if var in RESERVED_VARIABLES + (main_var, ): continue
            if var.startswith("@"):
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
        ADD_DETAILS = False

        if self.what in ("time_comparison", "strong_scaling"):
            ref_keys = {}
            for ref_var in ordered_vars:
                if ref_var in RESERVED_VARIABLES + (rolling_var, ): continue
                break # ref_var set to the first (main) variable
            ref_var = cfg.get('perf.cmp.ref_var', ref_var)
            ref_value = cfg.get('perf.cmp.ref_value', None)
            if ref_value is None:
                ref_value = str(variables.get(ref_var, ["<invalid ref_key>"])[0])
            if ADD_DETAILS:
                plot_title += f". Reference: <b>{ref_var}={ref_value}</b>"
            else:
                plot_title += f". Reference: {ref_value}"

        if ADD_DETAILS:
            plot_title += f" (colored by <b>{main_var}</b>"
            if second_var:
                plot_title += f", symbols by <b>{second_var}</b>"
            if rolling_var:
                plot_title += f", averaged by <b>{rolling_var}</b>"
            plot_title += ")"

        for entry in matrix_view.all_records(params, param_lists):
            if table_def is None:
                for table_key in entry.tables:
                    if not table_key.startswith(f"#{table}|"): continue
                    table_def = table_key
                    break
                else:
                    return {'layout': {'title': f"Error: no table named '{table_key}'"}}

                field_index = table_def.partition("|")[-1].split(",").index(field)
                row_index = 0

            entry.params.__x_var = entry.params.__dict__[cfg__x_var]

            time = entry.tables[table_def][1][row_index][field_index]

            if cfg__invert_time:
                entry.params.time = 1/time
            else:
                entry.params.time = time
                if self.mode == "specfem":
                    entry.params.time /= 60
                if self.mode == "gromacs":
                    entry.params.time *= 24

            ref_key = ""
            legend_name = ""
            for var in ordered_vars:
                if var in RESERVED_VARIABLES + (rolling_var, ): continue
                legend_name += f" {var}={params[var]}"

                if self.what in ("time_comparison", "strong_scaling"):
                    ref_key += f" {var}=" + str((params[var] if var != ref_var else ref_value))

            legend_name = legend_name.strip()

            if self.what in ("time_comparison", "strong_scaling"):
                ref_keys[legend_name] = ref_key.strip()

            main_var_value[legend_name] = entry.params.__dict__[main_var]
            second_var_value[legend_name] = entry.params.__dict__.get(second_var, None)

            if rolling_var is None:
                results[legend_name].append(entry.params)
            else:
                rolling_val = entry.params.__dict__[rolling_var]
                all_rolling_results[legend_name][f"{cfg__x_var}={entry.params.__x_var}"].append(entry.params)

            index_for_colors.add(main_var_value[legend_name])
            index_for_symbols.add(second_var_value[legend_name])
            line_color[legend_name] = lambda: COLORS(sorted(index_for_colors).index(entry_params.__dict__[main_var]))
            line_symbol[legend_name] = lambda: SYMBOLS[sorted(index_for_symbols).index(entry_params.__dict__[second_var])]

        x_max = 0
        y_max = 0
        y_min = 0
        def sort_key(legend_name):
            first_kv, _, other_kv = legend_name.partition(" ")
            if self.what in ("time_comparison", "strong_scaling"):
                first_kv, _, other_kv = other_kv.partition(" ")
            if not first_kv: return legend_name

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
                    entry_params_cpy.time_stdev = stats.stdev(times) if len(times) >= 2 else 0

                    results[legend_name].append(entry_params_cpy)

        if self.what in ("time_comparison", "strong_scaling"):
            ref_values = {}
            for ref_key in set(ref_keys.values()):
                if ref_key not in results:
                    print("MISSING", ref_key)
                    continue
                for entry_params in results[ref_key]:
                    if ref_key in ref_values: continue
                    if self.what in "time_comparison":
                        ref_values[ref_key + f" && {cfg__x_var}={entry_params.__x_var}"] = entry_params.time
                    else:
                        ref_values[ref_key] = entry_params.time*int(entry_params.__x_var)
        all_x = set()
        for legend_name in sorted(results.keys(), key=sort_key):
            x = []
            y = []
            if rolling_var is not None:
                err = []

            if self.what in ("speedup", "efficiency"):
                ref_machine_time = [100, 0]
                for entry_params in results[legend_name]:
                    if int(entry_params.__x_var) < ref_machine_time[0]:
                        ref_machine_time = [int(entry_params.__x_var), entry_params.time]
                ref_time = ref_machine_time[1]*ref_machine_time[0]

            for entry_params in sorted(results[legend_name], key=lambda ep:int(ep.__x_var)):
                if self.what == "time":
                    y_val = entry_params.time
                    if rolling_var is not None:
                        err.append(entry_params.time_stdev)
                elif self.what == "speedup":
                    y_val = ref_time/entry_params.time
                elif self.what == "efficiency":
                    y_val = (ref_time/entry_params.time)/int(entry_params.__x_var)
                elif self.what in ("time_comparison", "strong_scaling"):
                    ref_values_key = ref_keys[legend_name]
                    if self.what == "time_comparison":
                        ref_values_key += f" && {cfg__x_var}={entry_params.__x_var}"
                    try:
                        time_ref_value = ref_values[ref_values_key]
                    except KeyError:
                        y_val = None
                        #print("missing:", ref_values_key, ref_values.keys())
                    else:
                        time = entry_params.time
                        if self.what == "time_comparison":
                            y_val = (time-time_ref_value)/time_ref_value * 100
                        else:
                            y_val = (time_ref_value/time)/int(entry_params.__x_var)

                else:
                    raise RuntimeError(f"Invalid what: {self.what}")
                if y_val is None: continue
                x.append(int(entry_params.__x_var))
                y.append(y_val)

            x_max = max([x_max] + x)
            y_max = max([y_max] + [_y for _y in y if _y is not None])
            y_min = min([y_min] + [_y for _y in y if _y is not None])

            name = legend_name
            if name.startswith("platform="):
                name = name.partition("=")[-1]
            color = line_color[legend_name]()

            if self.what in ("time_comparison", "strong_scaling"):
                if legend_name in ref_keys.values():
                    showlegend = self.what == "strong_scaling"
                    if showlegend:
                        name += " (ref)"
                    trace = go.Scatter(x=x, y=y,
                                       name=name,
                                       legendgroup=main_var_value[legend_name],
                                       hoverlabel= {'namelength' :-1},
                                       showlegend=showlegend,
                                       mode='markers+lines',
                                       line=dict(color=color))
                    fig.add_trace(trace)
                    continue
                else:
                    # do not plot if no reference data available at all
                    if not [_y for _y in y if _y is not None]: continue

            try:
                symbol = line_symbol[legend_name]()
            except Exception:
                marker = dict(symbol="circle-dot")
            else:
                marker = dict(symbol=symbol,
                              size=8, line_width=2,
                              line_color="black", color=color)

            for inc in cfg__include_only:
                if inc in name:
                    break
            else:
                if cfg__include_only:
                    print(f"INFO: Skip '{name}'.")
                    continue


            trace = go.Scatter(x=x, y=y,
                               name=name,
                               legendgroup=main_var_value[legend_name],
                               hoverlabel= {'namelength' :-1},
                               mode='markers+lines',
                               line=dict(color=color),
                               marker=marker)
            fig.add_trace(trace)
            all_x.update(x)
            if rolling_var is not None:

                trace = go.Scatter(x=x, y=[_y - _err for _y, _err in zip(y, err)],
                                   name=name,
                                   legendgroup=main_var_value[legend_name],
                                   hoverlabel= {'namelength' :-1},
                                   showlegend=False, mode="lines",
                                   line=dict(color=color, width=0))

                fig.add_trace(trace)
                trace = go.Scatter(x=x, y=[_y + _err for _y, _err in zip(y, err)],
                                   name=name,
                                   legendgroup=main_var_value[legend_name],
                                   hoverlabel= {'namelength' :-1},
                                   fill='tonexty', showlegend=False, mode="lines",
                                   line=dict(color=color, width=0))
                fig.add_trace(trace)

        if self.what in ("efficiency", "strong_scaling"):
            trace = go.Scatter(x=[min(all_x), max(all_x)], y=[1, 1],
                               name="Linear",
                               showlegend=True,
                               hoverlabel= {'namelength' :-1},
                               mode='lines',
                               line=dict(color="black", width=1, dash="longdash"))
            fig.add_trace(trace)

        if self.what == "time":
            if self.mode == "gromacs":
                if cfg__invert_time:
                    y_title = "Simulation speed (ns/day)"
                    plot_title += " (higher is better)"
                else:
                    y_title = "Simulation time (hours of computation / ns simulated)"
                    plot_title += " (lower is better)"
            else:
                y_title = "Execution time (in minutes)"
                plot_title += " (lower is better)"
            y_min = 0
        elif self.what == "speedup":
            y_title = "Speedup ratio"
            plot_title += " (higher is better)"

        elif self.what in ("efficiency", "strong_scaling"):
            y_title = "Parallel Efficiency"
            plot_title += " (higher is better)"

        elif self.what == "time_comparison":
            y_title = "Time overhead (in %)"
            plot_title += " (lower is better)"

            if y_max == 0: y_max = 1

        fig.update_layout(
            title=plot_title, title_x=0.5,
            yaxis=dict(title=y_title, range=[y_min*1.01, y_max*1.01]),
            xaxis=dict(title=f"Number of {cfg__x_var}", range=[0, x_max+1]))

        if self.what in ("efficiency", "strong_scaling"):
            # use automatic Y range
            fig.update_layout(yaxis=dict(range=None))

        if cfg__legend_pos:
            try:
                top, right = cfg__legend_pos.split(",")
                top = float(top)
                right = float(right)
            except Exception:
                if cfg__legend_pos == "off":
                    fig.update_layout(showlegend=False)
                else:
                    print(f"WARNING: Could not parse 'perf.legend_pos={cfg__legend_pos}',"
                          " ignoring it. Expecting =TOP,RIGHT")
            else:
                print(f"INFO: Using legend position top={top}, right={right}")
                fig.update_layout(legend=dict(
                    yanchor="top", y=top,
                    xanchor="right", x=right,
                ))

        return fig, ""
