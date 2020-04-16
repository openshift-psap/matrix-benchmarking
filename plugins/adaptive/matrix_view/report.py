import dash_html_components as html
import dash_core_components as dcc

from ui.table_stats import TableStats
from ui.matrix_view import join

class Report():
    def __init__(self, id_name, name, **kwargs):
        self.id_name = id_name
        self.name = name
        self.kwargs = kwargs

        TableStats._register_stat(self)
        self.no_graph = True

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "" # nothing can be done here ...

    def do_report(self, *args):
        return f"nothing configured to generate the report for {self.name} ..."

    @classmethod
    def Decode(clazz, key_var, *args, **kwargs):
        obj = clazz(f"report_{key_var}_decode", f"Report: Decoding vs {key_var.title()}",
                    *args, **kwargs)

        obj.do_report = lambda *_args: obj.report_decode(key_var, *_args)

        return obj

    @classmethod
    def CPU(clazz, key_var, *args, **kwargs):
        obj = clazz(f"report_{key_var}_cpu", f"Report: Guest/Client CPU vs {key_var.title()}",
                    *args, **kwargs)

        obj.do_report = lambda *_args: obj.report_cpu(key_var, *_args)

        return obj

    @classmethod
    def GuestCPU(clazz, *args, **kwargs):
        obj = clazz(f"report_guest_cpu", f"Report: Guest CPU",
                    *args, **kwargs)

        obj.do_report = lambda *_args: obj.report_guest_cpu(*_args)

        return obj

    @classmethod
    def GPU(clazz, key_var, sys, engine, *args, **kwargs):
        kwargs['sys'] = sys
        kwargs['engine'] = engine
        obj = clazz(f"report_{key_var}_gpu_{sys}_{engine}", f"Report: {sys.title()} GPU {engine.title()} vs {key_var.title()}",
                    *args, **kwargs)

        obj.do_report = lambda *_args: obj.report_gpu(key_var, *_args)

        return obj

    @staticmethod
    def prepare_args(args, what, value):
        ordered_vars, params, param_lists, variables, cfg = args

        _ordered_vars = ordered_vars[:]
        try: _ordered_vars.remove(what)
        except ValueError: pass # 'what' wasn't in the list

        _variables = dict(variables)
        if what:
            params[what] = value
            _variables[what] = {value}

        _param_lists = [[(key, v) for v in _variables[key]] for key in ordered_vars]

        return _ordered_vars, params, _param_lists, _variables, cfg

    def do_plot(self, *args):
        ordered_vars, params, param_lists, variables, cfg = args

        print("Generate", self.name, "...")

        header = [html.P("---")]
        for k, v in params.items():
            if k == "stats": continue
            if v != "---": header.insert(0, html.Span([html.B(k), "=", v, ", "]))
            else: header.append(html.P([html.B(k), "=",
                                       ", ".join(map(str, variables[k]))]))
        header += [html.Hr()]
        header.insert(0, html.H1(self.name))

        report = self.do_report(*args)

        print("Generate: done!")

        return {}, header + report

    def report_decode(self, key_var, *args):
        ordered_vars, params, param_lists, variables, cfg = args

        if key_var not in ordered_vars:
            return [f"ERROR: {key_var} must not be set for this report."]

        def do_plot(stat_name, what, value):
            _args = Report.prepare_args(args, what, value)
            reg_stats = TableStats.stats_by_name[stat_name].do_plot(*_args)

            return [dcc.Graph(figure=reg_stats[0])] + reg_stats[1] + [html.Hr()]

        what = ordered_vars[0]
        if what == key_var: what = None
        by_what = f" (by {what})" if what else ""
        # --- Decode time --- #

        report = [html.H2(f"Decode Time" + by_what)]

        for value in variables.get(what, [params[what]]) if what else [""]:
            if what:
                report += [html.P(html.B(f"{what}={value}"))]

            report += do_plot(f"Reg: Client Decode Time vs {key_var.title()}", what, value)

        # --- Decode Time in Queue --- #

        report += [html.H2(f"Time in Queue" + by_what)]

        for value in variables.get(what, [params[what]]) if what else [""]:
            if what:
                report += [html.P(html.B(f"{what}={value}"))]

            report += do_plot(f"Reg: Time in Client Queue vs {key_var.title()}", what, value)

        # --- Client Queue --- #

        report += [html.H2(f"Client Queue Size")]
        report += do_plot("Client Queue", None, None)

        # --- Decode Duration --- #

        report += [html.H2(f"Decode Duration")]
        report += do_plot("Client Decode Duration", None, None)

        # --- Time between arriving frames --- #

        report += [html.H2(f"1/time between arriving frames")]
        report += do_plot("Client Framerate", None, None)

        # --- Frame Bandwidth --- #

        report += [html.H2(f"Frame Bandwidth" + by_what)]

        for value in variables.get(what, [params[what]]) if what else [""]:
            if what:
                report += [html.P(html.B(f"{what}={value}"))]
            report += do_plot(f"Reg: Frame Bandwidth vs {key_var.title()}", what, value)

        return report

    def report_gpu(self, key_var, *args):
        ordered_vars, params, param_lists, variables, cfg = args

        if key_var not in ordered_vars:
            return [f"ERROR: {key_var} must not be set for this report."]

        sys = self.kwargs["sys"]
        engine = self.kwargs["engine"]

        def do_plot(stat_name, what, value):
            _args = Report.prepare_args(args, what, value)
            reg_stats = TableStats.stats_by_name[stat_name].do_plot(*_args)
            if not reg_stats[0].data: return [False]

            return [dcc.Graph(figure=reg_stats[0])] + reg_stats[1] + [html.Hr()]

        what = ordered_vars[0]
        if what == key_var: what = None

        # --- GPU --- #
        report = [html.H2(f"{sys.capitalize()} GPU {engine} Usage"
                          + (f" (by {what})" if what else ""))]

        for value in variables.get(what, [params[what]]) if what else [""]:
            if what:
                report += [html.P(html.B(f"{what}={value}", what))]

            report += do_plot(f"Reg: {sys.capitalize()} GPU {engine} vs {key_var.title()}", what, value)
            if report[-1] is False:
                report.pop()
                report.append(html.I("Nothing ..."))

        return report

    def report_cpu(self, key_var, *args):
        ordered_vars, params, param_lists, variables, cfg = args

        if key_var not in ordered_vars:
            return [f"ERROR: {key_var} must not be set for this report."]

        def do_plot(stat_name, what, value):
            _args = Report.prepare_args(args, what, value)
            reg_stats = TableStats.stats_by_name[stat_name].do_plot(*_args)

            return [dcc.Graph(figure=reg_stats[0])] + reg_stats[1] + [html.Hr()]

        what = ordered_vars[0]
        if what == key_var: what = None

        # --- CPU --- #
        report = []
        SYST = ["guest", "client"]
        for src in SYST:
            report += [html.H2(f"{src.capitalize()} CPU Usage" + (f" (by {what})" if what else ""))]

            for value in variables.get(what, [params[what]]) if what else [""]:
                if what:
                    report += [html.P(html.B(f"{what}={value}"))]

                report += do_plot(f"Reg: {src.capitalize()} CPU vs {key_var.title()}", what, value)

        return report

    def report_guest_cpu(self, *args):
        ordered_vars, params, param_lists, variables, cfg = args

        def do_plot(stat_name):
            _args = Report.prepare_args(args, None, None)
            reg_stats = TableStats.stats_by_name[stat_name].do_plot(*_args)

            return reg_stats[1] + [dcc.Graph(figure=reg_stats[0])] + [html.Hr()]

        src = "guest"
        report = []

        equa = "CPU = " + " * ".join(f"({v.lower()} * {v[0].upper()})"for v in ordered_vars \
                                     if v != "experiment")
        report += []

        all_equa = []
        for key_var in "framerate", "resolution", "bitrate", "keyframe-period":
            report += [html.H3(f"{src.capitalize()} CPU Usage vs {key_var.title()}")]
            current_report = do_plot(f"Reg: {src.capitalize()} CPU vs {key_var.title()}")
            report += current_report
            all_equa += [e for e in current_report[:-2] if e and not isinstance(e, html.Br)]

        return ([html.B("Equation: "), html.I(f"{equa}"), html.Br()]
                + list(join(html.Br(), all_equa)) + [html.Hr()]
                + report)
