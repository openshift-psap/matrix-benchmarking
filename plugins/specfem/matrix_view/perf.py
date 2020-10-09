import plotly.graph_objs as go

from ui.table_stats import TableStats
from ui import matrix_view
from collections import defaultdict

from ui.matrix_view import COLORS

# https://plotly.com/python/marker-style/#custom-marker-symbols
SYMBOLS = {
    "32": "circle",
    "64": "cross",
    "96": "triangle-down",
    "128": "x",
    "192": "diamond",
    "256": "hexagram",
}

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
        
        index_for_colors = set()
        if "nex" not in variables and "nex" in params:
            plot_title += f" {params['nex']}nex"

        plot_title += f" (colored by {ordered_vars[-1]})"
        results = defaultdict(list)
        groups = {}
        symbols = {}
        line_color = {}

        if self.mode == "time_comparison":
            ref_keys = {}
            for ref_var in ordered_vars:
                if ref_var in ("machines", "mpi-slots"): continue
                break # ref_var set to the first (main) variable
            ref_var = cfg.get('perf.cmp.ref_var', ref_var)
            ref_value = cfg.get('perf.cmp.ref_value', None)
            if ref_value is None:
                ref_value = str(variables.get(ref_var, ["<invalid ref_key>"])[0])
            plot_title += f" (reference: {ref_var}={ref_value})"
            
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

            legend_name = f"{entry.params.platform}"
            if "nex" in variables:
                legend_name += f" | {entry.params.nex}nex"
                
            if self.mode == "time_comparison":
                ref_key = entry.params.platform if ref_var != "platform" else ref_value
                if "nex" in variables:
                    ref_key += " | " + (entry.params.nex if ref_var != "nex" else ref_value) + "nex"
                
            for var in ordered_vars:
                if var in ("machines", "mpi-slots", "nex", "platform"): continue
                legend_name += f" {var}={params[var]}"
                
                if self.mode == "time_comparison":
                    ref_key += f" {var}=" + str((params[var] if var != ref_var else ref_value))
                
            if self.mode == "time_comparison":
                ref_keys[legend_name] = ref_key
                
            if "nex" in variables:
                if self.mode != "time_comparison":
                    groups[legend_name] = entry.params.platform
                symbols[legend_name] = SYMBOLS[entry.params.nex]

            results[legend_name].append(entry.params)
            
            index_for_colors.add(entry.params.__dict__[ordered_vars[-1]])
            line_color[legend_name] = lambda: COLORS(sorted(index_for_colors).index(entry_params.__dict__[ordered_vars[-1]]))
            
                
        x_max = 0
        y_max = 0
        y_min = 0
        def sort_key(v):
            if "nex" not in variables: return v
            nex = int(v.split()[2].replace("nex", ""))
            plat = v.split()[0]
            return f"{plat} {nex:03}"

        if self.mode == "time_comparison":
            ref_values = {}

            for ref_key in set(ref_keys.values()):
                if ref_key not in results:
                    print("MISSING", ref_key)
                    #import pdb;pdb.set_trace()
                    continue
                for entry_params in results[ref_key]:
                    if ref_key in ref_values: continue
                    ref_values[ref_key + f" && machines={entry_params.machines}"] = entry_params.time
            
        for legend_name in sorted(results.keys(), key=sort_key):
            x = []
            y = []

            if self.mode in ("speedup", "efficiency"):
                ref_machine_time = [100, 0]
                for entry_params in results[legend_name]:
                    if int(entry_params.machines) < ref_machine_time[0]:
                        ref_machine_time = [int(entry_params.machines), entry_params.time]

                ref_time = ref_machine_time[1]/ref_machine_time[0]
                
            for entry_params in results[legend_name]:
                x.append(int(entry_params.machines))
                if self.mode == "time":
                    y_val = entry_params.time
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
                        print("missing:", ref_values_key, ref_values.keys())
                        #import pdb;pdb.set_trace()
                    else:
                        time = entry_params.time
                        y_val = (time_ref_value-time)/time_ref_value * 100
                else:
                    raise RuntimeError(f"Invalid mode: {self.mode}")
                
                y.append(y_val)
                    
            x_max = max([x_max] + x)
            y_max = max([y_max] + [_y for _y in y if _y is not None])
            y_min = min([y_min] + [_y for _y in y if _y is not None])

            name = legend_name
            if self.mode == "time_comparison":
                if legend_name in ref_keys.values():
                    name += " (reference)"

            color = line_color[legend_name]()
            if legend_name in symbols:
                marker = dict(symbol=symbols[legend_name],
                              size=8, line_width=2,
                              line_color="black", color=color)
            else:
                marker = dict(symbol="circle-dot")
                
            trace = go.Scatter(x=x, y=y,
                               name=name,
                               legendgroup=groups.get(legend_name, None),
                               hoverlabel= {'namelength' :-1},
                               mode='markers+lines',
                               line=dict(color=color),
                               marker=marker)
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
