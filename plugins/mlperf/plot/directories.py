
from dash import html
from common import Matrix
import matrix_view.table_stats

class Directories():
    def __init__(self, mig_type=None, speed=False):
        self.name = "Directories"

        self.id_name = self.name.lower()
        #self.no_graph = True

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        elts = [html.P(html.B(", ".join([f"{k}={v}" for k, v in params.items() if v != "---"])))]

        elements = {}
        for entry in Matrix.all_records(params, param_lists):
            gpu_name = entry.params.gpu_type
            li_elts = []

            key = " " + ", ".join([f"{k}={entry.params.__dict__[k]}" for k in reversed(ordered_vars)])

            if entry.is_gathered:
                for k, v in entry.gathered_keys.items():
                    key += f", {k}={{{' '.join(v)}}}"

            params = html.B(key)
            li_elts.append(html.A("link", href="file://"+entry.location))
            li_elts.append(html.Span(params))

            elements[key] = html.Li(li_elts)

        for k in sorted(elements):
            elts.append(elements[k])

        return None, html.Ul(elts)
