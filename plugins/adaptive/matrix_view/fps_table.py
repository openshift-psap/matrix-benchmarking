from collections import defaultdict

import dash_html_components as html
import dash_table
import plotly.graph_objs as go

from ui.table_stats import TableStats
from ui.matrix_view import natural_keys
from ui import matrix_view

class FPSTable():
    def __init__(self):
        self.name = "Table: FPS"
        self.id_name = "table_fps"
        TableStats._register_stat(self)
        self.no_graph = True

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        layout = go.Layout(meta=dict(name=self.name))

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

        fps_target = defaultdict(lambda:defaultdict(dict))
        fps_actual = defaultdict(lambda:defaultdict(dict))

        min_fps = 120
        max_fps = 0
        for entry in matrix_view.all_records(params, param_lists):
            x_key = " ".join([f'{v}={params[v]}' for v in reversed(second_vars) if v not in (subtables_var, y_var)])
            y_key = f'{y_var}={params[y_var]}' if y_var else None

            subtable_name = subtables[params[subtables_var]] if subtables_var else None
            fps_target[subtable_name][y_key][x_key] = int(params['framerate']) \
                if 'framerate' in params else None

            fps_actual[subtable_name][y_key][x_key] = fps = int(entry.stats["Guest Framerate"].value)
            min_fps = min(min_fps, fps)
            max_fps = max(max_fps, fps)

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

        for i, (subtable_name, xy_values) in enumerate(fps_actual.items()):
            columns = [{"id":"title", "name":""}]
            data_dicts = []
            first_pass = True
            fps_values = set()
            for y_key, x_values in xy_values.items():
                current_dict = {"title": y_key}
                data_dicts.append(current_dict)

                for x_key, fps in x_values.items():
                    if first_pass: columns.append(dict(id=x_key, name=x_key))
                    current_dict[x_key] = fps
                    fps_values.add(fps)
                first_pass = False

            color_filters = []
            for c in columns:
                if c['id'] == 'title': continue
                for fps in fps_values:
                    fps_pos = (fps-min_fps)/(max_fps-min_fps)
                    color = "rgb("+", ".join([str(int(c*255)) for c in elev_cmap(1-fps_pos)[:3]])+")"
                    color_filters.append({'if': {'column_id': c['id'],
                                                 'filter_query': f"{{{c['id']}}} eq '{fps}'"},
                                          'backgroundColor': color},)


            if subtable_name:
                tables.append(html.B(subtable_name))
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

        return {}, [html.H2(f"{self.name} vs " + " x ".join(ordered_vars)),
                    html.B(f"FPS between {min_fps} and {max_fps}.")] + tables
