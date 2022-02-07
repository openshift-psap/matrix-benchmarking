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
        cfg__weak_scaling = cfg.get('perf.weak_scaling', False)
        cfg__remove_details = cfg.get('perf.rm_details', False)

        try:
            cfg__x_var = cfg['perf.x_var']
            print(f"INFO: using {cfg__x_var} as X variable")
        except KeyError:
            cfg__x_var = "machines"

        if cfg__include_only:
            cfg__include_only = cfg__include_only.split(",")
            print(f"INFO: Include only '{', '.join(cfg__include_only)}' platforms.")

        plot_title = f"{self.mode.title()}"

        if cfg__weak_scaling:
            plot_title += f" Weak Scaling"

        if cfg__invert_time and self.what == "time":
            plot_title += f" Simulation Speed"
        else:
            if self.mode == "gromacs":
                plot_title += " Simulation"
            if self.mode == "specfem" and self.what == "time":
                plot_title += " Execution"

            if self.what == "strong_scaling":
                plot_title += " Efficiency"
            else:
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
        if cfg__weak_scaling:
            weak_values = {}

        main_var_value = {}
        second_var_value = {}
        line_symbol = {}
        line_color = {}


        if self.what in ("time_comparison", "strong_scaling"):
            ref_keys = {}
            for ref_var in ordered_vars:
                if ref_var in RESERVED_VARIABLES + (rolling_var, ): continue
                break # ref_var set to the first (main) variable
            ref_var = cfg.get('perf.cmp.ref_var', ref_var)
            ref_value = cfg.get('perf.cmp.ref_value', None)
            if ref_value is None:
                ref_value = str(variables.get(ref_var, ["<invalid ref_key>"])[0])
            if cfg__remove_details:
                plot_title += f". Reference: {ref_value}"
            else:
                plot_title += f". Reference: <b>{ref_var}={ref_value}</b>"

        if not cfg__remove_details:
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
            if cfg__weak_scaling:
                weak_key = f"{cfg__x_var}={entry.params.__x_var}"
                try:
                    nex = weak_values[weak_key]
                except KeyError:
                    if int(entry.params.nex) not in weak_values.values():
                        weak_values[weak_key] = int(entry.params.nex)
                    else:
                        weak_values[weak_key] = 0
                else:
                    if int(entry.params.nex) > nex:
                        if int(entry.params.nex) not in weak_values.values():
                            weak_values[weak_key] = int(entry.params.nex)
                        else:
                            weak_values[weak_key] = 0

                            if int(entry.params.nex) == 256:
                                weak_values[weak_key] = int(entry.params.nex)
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
                key = f"{cfg__x_var}={entry.params.__x_var}"
                all_rolling_results[legend_name][key].append(entry.params)
                pass

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
            if not first_kv:
                if cfg__weak_scaling:
                    return 1
                return legend_name

            k, v = first_kv.split("=")
            try: new_v = "{:20}".format(int(v))
            except Exception: new_v = v

            pos = {"baremetal": 0,
                   "openshift_hostnet": 1,
                   "openshift_multus": 2,
                   "openshift_snd": 3}

            try:
                nex = int(other_kv.split("=")[1])
            except Exception:
                return -1

            return pos.get(new_v, 10) * 1000 + 256-nex

            return f"{new_v} {other_kv}"

        if rolling_var is not None:
            for legend_name, rolling_results in all_rolling_results.items():
                for machine_count, entries_params in rolling_results.items():
                    times = []
                    for entry_params in entries_params:
                        if cfg__weak_scaling:
                            weak_key = f"{cfg__x_var}={entry_params.__x_var}"
                            if weak_values[weak_key] != int(entry_params.nex): continue
                        times.append(entry_params.time)
                    # shallow copy of the last entry_params
                    entry_params_cpy = entry_params.__class__(**entry_params.__dict__)
                    entry_params_cpy.time = stats.mean(times) if len(times) >= 1 else 0
                    entry_params_cpy.time_stdev = stats.stdev(times) if len(times) >= 2 else 0

                    results[legend_name].append(entry_params_cpy)
                    if cfg__weak_scaling:
                        weak_legend_name = " ".join([kv for kv in legend_name.split() if not kv.startswith("nex=")])
                        results[weak_legend_name].append(entry_params_cpy)
                        line_symbol[weak_legend_name] = lambda: None
                        line_color[weak_legend_name] = line_color[legend_name]
                        main_var_value[weak_legend_name] = weak_legend_name
        ref_values = {}
        if self.what in ("time_comparison", "strong_scaling"):
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

        elif self.what in ("speedup", "efficiency"):
            for legend_name in sorted(results.keys(), key=sort_key):
                if cfg__weak_scaling and "nex=" not in legend_name:
                    continue
                ref_value = None
                for entry_params in results[legend_name]:
                    if not ref_value or int(entry_params.__x_var) < int(ref_value.__x_var):
                        ref_value = entry_params
                ref_values_key = f"{legend_name} {cfg__x_var}={entry_params.__x_var}"
                ref_values[legend_name] = ref_value

            for legend_name in sorted(results.keys(), key=sort_key):
                if not cfg__weak_scaling or "nex=" in legend_name:
                    continue
                #import pdb;pdb.set_trace()
                for entry_params in results[legend_name]:
                    weak_key = f"{cfg__x_var}={entry_params.__x_var}"
                    ref_nex = weak_values[weak_key]
                    ref_values_key = f"{legend_name} {weak_key}"
                    ref_values[ref_values_key] = ref_values[f"{legend_name} nex={entry_params.nex}"]

        all_x = set()

        for legend_name in sorted(results.keys(), key=sort_key):
            x = []
            y = []
            if rolling_var is not None:
                err = []

            for entry_params in sorted(results[legend_name], key=lambda ep:int(ep.__x_var)):
                if cfg__weak_scaling:
                    weak_key = f"{cfg__x_var}={entry_params.__x_var}"
                    if weak_values[weak_key] != int(entry_params.nex): continue

                if self.what in ("speedup", "efficiency"):
                    ref_values_key = f"{legend_name}"
                    if cfg__weak_scaling and "nex=" not in legend_name:
                        ref_values_key += f" {cfg__x_var}={entry_params.__x_var}"
                    ref_value = ref_values[ref_values_key]
                    ref_time = ref_value.time * int(ref_value.__x_var)

                if self.what == "time":
                    y_val = entry_params.time
                    if rolling_var is not None:
                        err.append(entry_params.time_stdev)
                elif self.what == "speedup":
                    y_val = ref_time/entry_params.time
                elif self.what == "efficiency":
                    y_val = (ref_time/entry_params.time)/int(entry_params.__x_var)
                elif self.what in ("time_comparison", "strong_scaling"):
                    ref_keys_key = legend_name
                    if cfg__weak_scaling and "nex=" not in legend_name:
                        ref_nex = weak_values[weak_key]
                        ref_keys_key += f" nex={ref_nex}"
                    ref_values_key = ref_keys[ref_keys_key]

                    if self.what == "time_comparison":
                        ref_values_key += f" && {cfg__x_var}={entry_params.__x_var}"
                    try:
                        time_ref_value = ref_values[ref_values_key]
                    except KeyError:
                        y_val = None

                        print("missing:", ref_values_key, "IN", ', '.join(ref_values.keys()))
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

            name = legend_name
            if name.startswith("platform="):
                name = name.partition("=")[-1]
            color = line_color[legend_name]()

            if self.what in ("time_comparison", "strong_scaling"):
                if legend_name in ref_keys.values():
                    showlegend = False

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
                if symbol is not None:
                    marker = dict(symbol=symbol,
                                  size=8, line_width=2,
                                  line_color="black", color=color)
                else:
                    marker = dict()

            for inc in cfg__include_only:
                if inc in name:
                    break
            else:
                if cfg__include_only:
                    print(f"INFO: Skip '{name}'.")
                    continue

            x_max = max([x_max] + x)
            y_max = max([y_max] + [_y for _y in y if _y is not None])
            y_min = min([y_min] + [_y for _y in y if _y is not None])

            trace = go.Scatter(x=x, y=y,
                               name=name,
                               showlegend=True,
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
        if self.what in ("speedup"):
            trace = go.Scatter(x=[0, max(all_x)], y=[0, max(all_x)],
                               name="Linear",
                               showlegend=True,
                               hoverlabel= {'namelength' :-1},
                               mode='lines',
                               line=dict(color="black", width=2, dash="longdash"))
            fig.add_trace(trace)
        elif self.what in ("efficiency", "strong_scaling"):
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
