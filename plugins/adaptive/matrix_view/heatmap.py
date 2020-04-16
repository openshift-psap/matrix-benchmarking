import plotly.graph_objs as go

from ui.table_stats import TableStats
from ui.matrix_view import COLORS
from ui import matrix_view

class HeatmapPlot():
    def __init__(self, name, table, title, x, y):
        self.name = "Heat: "+name
        self.id_name = name
        TableStats._register_stat(self)
        self.table = table
        self.title = title
        self.x = x
        self.y = y

    def do_hover(self, meta_value, variables, figure, data, click_info):
        name = figure['data'][click_info.idx]['name']

        if name == 'heatmap':
            z = data['points'][0]['z']
            return (f"Cannot get link to viewer for Heatmap layer. "
                    f"Try to hide it with double clicks ... "
                    f"[x: {click_info.x}, y: {click_info.y}, z: {z:.0f}%]")

        props = name.split(", ") if name else []

        value = f"[x: {click_info.x}, y: {click_info.y}]"

        return TableStats.props_to_hoverlink(variables, props, value)

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        table_def = None
        fig = go.Figure()
        all_x = []
        all_y = []

        if len(variables) > 4:
            return {'layout': {'title': f"Too many variables selected ({len(variables)} > 4)"}}

        for i, entry in enumerate(matrix_view.all_records(params, param_lists)):
            if table_def is None:
                for table_key in entry.tables:
                    if not table_key.startswith(f"#{self.table}|"): continue
                    table_def = table_key
                    break
                else:
                    return {'layout': {'title': f"Error: no table named '{table_key}'"}}

            table_fields = table_def.partition("|")[-1].split(";")
            try:
                x_row_id = table_fields.index(self.x[0])
                y_row_id = table_fields.index(self.y[0])
            except ValueError:
                return {'layout': {'title': f"Error: Could not find {self.x}/{self.y} in '{table_def}'"}}
            table_rows = entry.tables[table_def]
            x = [row[x_row_id] * self.x[2] for row in table_rows[1]]
            y = [row[y_row_id] * self.y[2] for row in table_rows[1]]

            if 'heat.min_x' in cfg or 'heat.max_x' in cfg:
                min_x = cfg.get('heat.min_x', min(x))
                max_x = cfg.get('heat.max_x', max(x))

                new_x = []
                new_y = []
                for _x, _y in zip(x, y):
                    if not (min_x <= _x <= max_x): continue
                    new_x.append(_x)
                    new_y.append(_y)
                x = new_x
                y = new_y

            name =  ", ".join(f"{k}={params[k]}" for k in variables)
            if not name: name = "single selection"
            all_x += x
            all_y += y

            if len(variables) < 3:
                fig.add_trace(go.Scatter(
                    xaxis = 'x', yaxis = 'y', mode = 'markers',
                    marker = dict(color = COLORS(i), size = 3 ),
                    name=name, legendgroup=name,
                    x = x, y = y,
                    hoverlabel= {'namelength' :-1}
                ))

            fig.add_trace(go.Histogram(
                xaxis = 'x2', marker = dict(color=COLORS(i)), showlegend=False, opacity=0.75,
                histnorm='percent',
                y = y, legendgroup=name, name=name,
                hoverlabel= {'namelength' :-1},
            ))
            fig.add_trace(go.Histogram(
                yaxis = 'y2', marker = dict(color=COLORS(i)), showlegend=False, opacity=0.75,
                x = x, legendgroup=name, name=name,
                histnorm='percent',
                hoverlabel= {'namelength' :-1}
            ))

        fig.add_trace(go.Histogram2d(
            xaxis='x', yaxis='y',
            x=all_x, y=all_y, name='heatmap', histnorm='percent',
            showscale=False,
            colorscale=[[0, '#e5ecf6'], # carefully chosen with gimp to match the plot background color
                        [0.1, '#e5ecf6'], # more or less hide the first 10%
                        [0.5, 'rgb(242,211,56)'], [0.75, 'rgb(242,143,56)'], [1, 'rgb(217,30,30)']]
        ))

        fig.update_layout(
            meta=dict(name=self.name),
            barmode='overlay',
            xaxis=dict(
                zeroline=True, showgrid=False, rangemode='tozero',
                domain=[0,0.85],
                title=self.x[1],
            ),
            yaxis=dict(
                zeroline=True, showgrid =False, rangemode='tozero',
                domain=[0,0.85],
                title=self.y[1],
            ),
            xaxis2=dict(
                zeroline=True, showgrid=False,
                domain=[0.85,1],
                title='% of frames',
            ),
            yaxis2=dict(
                zeroline=True, showgrid=False,
                domain=[0.85,1],
                title='% of frames',
            ),
            bargap=0, hovermode='closest',
            showlegend=True, title=self.title + " (in %)",
        )
        return fig, ""
