from collections import defaultdict

import plotly.graph_objs as go
import dash_table
import dash_core_components as dcc
import dash_html_components as html

import numpy as np

from ui.table_stats import TableStats
from ui.matrix_view import natural_keys, join
from ui import matrix_view

Regression = None # populated in __init__.py:register

class ModelGuestCPU():
    def __init__(self):
        self.name = "Model: Guest CPU Usage"
        self.id_name = "model_guest_cpu"
        self.no_graph = True
        self.estimate_value = self.estimate_guest_cpu_value

        TableStats._register_stat(self)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing ..."

    @staticmethod
    def estimate_guest_gpu_render_value(params={}, formula=False):
        "Guest GPU Render"

        if params.get('display') == "webgl-wipeout":
            aFR, aF, aR = -0.033, 0.48, 27.28
        elif params.get('display') == "img-lady-1920":
            aFR, aF, aR= 0.15, 0.25, 0.19
        else:
            return float('+inf')

        if formula:
            return (f"gpu_render = framerate * resolution * {aFR:.2f} "
                    f"+ framerate * {aF:.2f} "
                    f"+ resolution * {aR:.2f}")

        resolution = params.get('res',
                                Regression.res_in_mpix(params.get('resolution', "1920x1080")))
        framerate = params['framerate']

        return framerate * resolution * aFR + framerate * aF + resolution * aR

    @staticmethod
    def estimate_guest_cpu_value(params={}, formula=False):
        "Guest CPU"

        COEFFS = {"webgl-wipeout": 0.21,
                  "img-lady-1920": 0.13}

        try: coeff = COEFFS[params['display']]
        except KeyError: return float('+inf')

        if formula is True: return f"CPU = resolution x framerate x {coeff:.2f}"

        if params.get('rate-control', 'cbr') != 'cbr': return float('+inf')

        resolution = params.get('res',
                                Regression.res_in_mpix(params.get('resolution', "1920x1080")))
        framerate = params['framerate']

        #bitrate = Regression.bitrate_in_mbps(params['bitrate'])
        #kfr = params['keyframe-period']

        return resolution*framerate*coeff

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        layout = go.Layout(meta=dict(name=self.name))

        actual_key = self.estimate_value.__doc__

        second_vars = ordered_vars[:]
        second_vars.reverse()

        subtables = {}
        if len(second_vars) > 2:
            subtables_var = second_vars[-1]
            y_var = second_vars[-2]

            for subtable_key in sorted(variables[subtables_var], key=natural_keys):
                subtables[subtable_key] = f"{subtables_var}={subtable_key}"

        elif len(second_vars) == 2:
            subtables_var = None
            y_var = second_vars[-1]
        else:
            subtables_var = None
            y_var = None

        values = defaultdict(lambda:defaultdict(dict))

        min_dist = float('+inf')
        max_dist = float('-inf')
        dist_count = [0, 0]
        value_units = ""

        for entry in matrix_view.all_records(params, param_lists):
            x_key = " ".join([f'{v}={params[v]}' for v in reversed(second_vars) \
                              if v not in (subtables_var, y_var)])
            y_key = f'{y_var}={params[y_var]}' if y_var else None

            subtable_name = subtables[params[subtables_var]] if subtables_var else None

            estimated_value = self.estimate_value(params)
            actual_value = entry.stats[actual_key].value
            if not value_units:
                unit = TableStats.stats_by_name[actual_key].unit
                value_units = f" (in {unit})"
            dist = estimated_value - actual_value

            values[subtable_name][y_key][x_key] = estimated_value, actual_value

            if abs(estimated_value) != float('inf'):
                min_dist = min(min_dist, dist)
                max_dist = max(max_dist, dist)
                dist_count[0] += 1
                dist_count[1] += abs(dist)

        colors = ['rgb(239, 243, 255)', 'rgb(189, 215, 231)', 'rgb(107, 174, 214)',
                  'rgb(49, 130, 189)', 'rgb(8, 81, 156)']

        def colormap_to_colorscale(cmap):
            from matplotlib import colors
            #function that transforms a matplotlib colormap to a Plotly colorscale
            return [ [k*0.1, colors.rgb2hex(cmap(k*0.1))] for k in range(11)]

        def colorscale_from_list(alist, name):
            from matplotlib.colors import LinearSegmentedColormap
            # Defines a colormap, and the corresponding Plotly colorscale from the list alist
            # alist=the list of basic colors
            # name is the name of the corresponding matplotlib colormap

            cmap = LinearSegmentedColormap.from_list(name, alist)
            #display_cmap(cmap)
            colorscale = colormap_to_colorscale(cmap)
            return cmap, colorscale

        elevation =['#31A354', '#F7FCB9']

        elev_cmap, elev_cs = colorscale_from_list(elevation, 'elev_cmap')
        # ---

        tables = []

        for i, (subtable_name, xy_values) in enumerate(values.items()):
            columns = [{"id":"title", "name":""}]
            data_dicts = []
            first_pass = True
            current_dists = set()
            for y_key, x_values in xy_values.items():
                current_dict = {"title": y_key}
                data_dicts.append(current_dict)
                for x_key, (estimated_value, actual_value) in x_values.items():
                    if first_pass: columns.append(dict(id=x_key, name=x_key))
                    if abs(estimated_value) != float('inf'):
                        dist = estimated_value - actual_value
                        current_dict[x_key] = f"estim: {estimated_value:.0f}% | actual: {int(actual_value)}% | error: {dist:+.1f}%"
                    else:
                        dist = None
                        current_dict[x_key] = f"estim: ---% | actual: {int(actual_value)}% | error: ---%"

                    current_dists.add((current_dict[x_key], dist))
                first_pass = False

            color_filters = []
            for c in columns:
                if c['id'] == 'title': continue
                for val, dist in current_dists:
                    if dist is not None:
                        dist_pos = abs(dist)/max(abs(max_dist), abs(min_dist))
                        color = "rgb("+", ".join([str(int(c*255)) for c in elev_cmap(dist_pos)[:3]])+")"
                    else:
                        color = "#f08080"
                    color_filters.append({'if': {'column_id': c['id'],
                                                 'filter_query': f"{{{c['id']}}} eq '{val}'"},
                                          'backgroundColor': color},)


            if subtable_name:
                tables.append(html.B(subtable_name))
                print(f"# {subtable_name}")

            x = []; y = []; z = [];
            x_estim = []; y_estim = []; z_estim = []
            for y_key, x_values in xy_values.items():
                y_estim.append(y_key)
                z_estim.append([])
                for x_key, (estimated_value, actual_value) in x_values.items():
                    if x_key not in x_estim:
                        x_estim.append(x_key)
                    x.append(x_key)
                    y.append(y_key)
                    z.append(actual_value)
                    z_estim[-1].append(estimated_value)
                x.append(None)
                y.append(None)
                z.append(None)

            tables.append(dcc.Graph(figure=go.Figure(data=[
                go.Scatter3d(x=x, y=y, z=z, name="Actual"),
                go.Surface(x=x_estim, y=y_estim,
                           z=z_estim, name="Estimated"),
            ])))

            tables.append(
                dash_table.DataTable(
                    sort_action="native",
                    style_cell_conditional=color_filters,
                    style_header={
                        'backgroundColor': 'white',
                        'fontWeight': 'bold'
                    },
                    style_as_list_view=True,
                    id='data-table',
                    columns=columns,
                    data=data_dicts,
                )
            )

        formula = self.estimate_value(formula=True)
        return {}, [html.H2(f"{self.name} vs " + " x ".join(ordered_vars)),
                    html.B(f"Error distance between {min_dist:.0f}% and {max_dist:.0f}% for {dist_count[0]} measures. "
                           f"{formula} | error sum = {dist_count[1]:.0f}"),

                    html.Br()] + tables


class PlotModel(ModelGuestCPU):
    def __init__(self, name, id_name, estimate_value_fct, *args, **kwargs):
        self.name = f"PlotModel: {name}"
        self._name = name
        self.id_name = f"plot_model_{id_name}"
        self.no_graph = False
        self.estimate_value = estimate_value_fct

        TableStats._register_stat(self)

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        actual_key = self.estimate_value.__doc__
        max_x, max_y = 0, 0

        def colormap_to_colorscale(cmap):
            from matplotlib import colors
            #function that transforms a matplotlib colormap to a Plotly colorscale
            return [ [k*0.1, colors.rgb2hex(cmap(k*0.1))] for k in range(11)]

        def colorscale_from_list(alist, name):
            from matplotlib.colors import LinearSegmentedColormap
            # Defines a colormap, and the corresponding Plotly colorscale from the list alist
            # alist=the list of basic colors
            # name is the name of the corresponding matplotlib colormap

            cmap = LinearSegmentedColormap.from_list(name, alist)
            #display_cmap(cmap)
            colorscale = colormap_to_colorscale(cmap)
            return cmap, colorscale

        elevation =['green', "red"]

        elev_cmap, elev_cs = colorscale_from_list(elevation, 'elev_cmap')

        traces = []
        max_dist = 0
        min_dist = 100
        value_units = f" (in {TableStats.stats_by_name[actual_key].unit})"
        for entry in matrix_view.all_records(params, param_lists):
            estimated_value = self.estimate_value(params)
            actual_value = entry.stats[actual_key].value
            dist = estimated_value - actual_value

            x = [Regression.res_in_mpix(params['resolution'])] * 2
            y = [params['framerate']]*2
            z = [estimated_value, actual_value]

            max_x = max(max_x, x[0])
            max_y = max(max_y, y[0])
            if abs(dist) == float('inf'): continue

            max_dist = max(max_dist, dist)
            min_dist = min(min_dist, dist)

            traces.append((x, y, z, f"err={dist:.0f}% | {entry.key}", dist))

        data = []
        for x, y, z, key, dist in traces:
            dist_pos = abs(dist/max_dist)
            color = "rgb("+", ".join([str(int(c*255)) for c in elev_cmap(dist_pos)[:3]])+")"
            data.append(go.Scatter3d(x=x, y=y, z=z, name=key, mode="lines",
                                     line=dict(width=10, color=color),
                                     showlegend=False, hoverlabel= {'namelength' :-1},))

            data.append(go.Scatter3d(x=[x[1]], y=[y[1]], z=[z[1]], name=key, mode="markers",
                                     marker=dict(size=5, color=color),
                                     showlegend=False, hoverlabel= {'namelength' :-1},))
        LENGTH = 50
        estim_x = np.linspace(0.0, max_x, LENGTH)
        estim_y = np.linspace(0.0, max_y, LENGTH)
        estim_z = [[100]*LENGTH for _ in range(LENGTH)]
        formulae = []
        for disp in variables.get('display', [params['display']]):
            cur_params = {"display": disp}
            formula = self.estimate_value(cur_params, formula=True)
            if formula is None: continue

            for i, _x in enumerate(estim_x):
                for j, _y in enumerate(estim_y):
                    cur_params['res'] = _x
                    cur_params['framerate'] = _y
                    estim_z[j][i] = self.estimate_value(cur_params)

            formula = f"display={disp} | {formula}"
            data += [go.Surface(x=estim_x, y=estim_y, z=estim_z, name=formula,
                                showscale=False,
                                hoverlabel= {'namelength' :-1})]
            formulae += [formula]
        fig = go.Figure(data=data)

        fig.update_layout(
            title={
                'text': self._name,
                'y':0.9, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top'},
            scene=dict(
                xaxis_title="Resolution (in Mpix)",
                yaxis_title="Framerate",
                zaxis_title=f"{actual_key}{value_units}"))
        fig.write_html("/tmp/model_cpu.html")
        return fig, [f"Error between {min_dist:.0f}% and {max_dist:.0f}% ({len(traces)} measurements).", html.Br()] + list(join(html.Br(), formulae))
