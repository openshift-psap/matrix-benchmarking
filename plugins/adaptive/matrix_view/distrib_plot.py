import plotly.graph_objs as go

from ui.table_stats import TableStats
from ui import matrix_view


class DistribPlot():
    def __init__(self, name, table, x, x_unit, divisor=1):
        self.name = "Distrib: "+name
        self.id_name = name
        TableStats._register_stat(self)
        self.table = table
        self.x = x
        self.x_unit = x_unit
        self.divisor = divisor

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        table_def = None
        fig = go.Figure()

        use_count = bool(cfg.get('distrib.count'))
        show_i_vs_p = str(cfg.get('distrib.i_vs_p', "").lower())
        side_by_side = bool(cfg.get('distrib.side'))

        if len(variables) > 4:
            return {'layout': {'title': f"Too many variables selected ({len(variables)} > 4)"}}

        for entry in matrix_view.all_records(params, param_lists):
            if table_def is None:
                for table_key in entry.tables:
                    if not table_key.startswith(f"#{self.table}|"): continue
                    table_def = table_key
                    break
                else:
                    return {'layout': {'title': f"Error: no table named '{table_key}'"}}
                tname = table_def.partition("|")[0].rpartition(".")[-1]

                if not show_i_vs_p: continue
                if "key_frame" not in table_def:
                    return {'layout': {'title': f"key_frame field not found in {table_def}"}}

                kfr_row_id = table_def.partition("|")[2].split(";").index(f"{tname}.key_frame")


            table_fields = table_def.partition("|")[-1].split(";")

            x_row_id = table_fields.index(self.x)
            table_rows = entry.tables[table_def]

            histnorm = None if use_count else 'percent'
            legend_name = " ".join([f"{var}={params[var]}" for var in ordered_vars])
            if not show_i_vs_p:
                x = [row[x_row_id]/self.divisor for row in table_rows[1]]
                fig.add_trace(go.Histogram(x=x, histnorm=histnorm, name=legend_name))

            elif kfr_row_id:
                xi = [row[x_row_id]/self.divisor for row in table_rows[1] if row[kfr_row_id]]
                xp = [row[x_row_id]/self.divisor for row in table_rows[1] if not row[kfr_row_id]]

                if show_i_vs_p in ("1", "I", "i"):
                    fig.add_trace(go.Histogram(x=xi, histnorm=histnorm, name=legend_name+" | I-frames"))
                if show_i_vs_p in ("1", "P", "p"):
                    fig.add_trace(go.Histogram(x=xp, histnorm=histnorm, name=legend_name+" | P-frames"))

        fig.update_layout(
            title=self.name,
            yaxis=dict(title="Distribution "+("(in # of frames)" if use_count else "(in %)")),
            xaxis=dict(title=f"{self.id_name} (in {self.x_unit})"))

        if not side_by_side:
            fig.update_layout(barmode='stack')

        return fig, ""
