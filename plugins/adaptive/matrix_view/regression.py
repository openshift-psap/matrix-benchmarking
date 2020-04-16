import math
from collections import defaultdict

import scipy
import scipy.stats

import plotly.graph_objs as go
import dash_html_components as html

import numpy as np

from ui.table_stats import TableStats
from ui.matrix_view import join, COLORS
from ui import matrix_view

class Regression():
    @staticmethod
    def FPS(val):
        "FPS"
        return val

    def keyframe_period(val):
        "kfp"
        return val

    @staticmethod
    def bitrate_in_mbps(bitrate):
        "MB/s"
        return int(bitrate)/8/1024

    @staticmethod
    def res_in_mpix(res):
        "Mpx" # docstring

        x, y = map(int, res.split("x"))

        return x*y * 10**-6

    def __init__(self, id_name, key_var, name, x_key, y_key):
        self.name = "Reg: " + name
        self.id_name = id_name
        self.x_key = x_key
        self.y_key = y_key
        self.key_var = key_var

        TableStats._register_stat(self)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return ""

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        MIN_COUNT_FOR_REGR = 4
        fig = go.Figure()

        x = defaultdict(list)
        y = defaultdict(list)
        text = defaultdict(list)

        reg_x, reg_y = defaultdict(list), defaultdict(list)
        fixed_params = {}

        other_vars = ordered_vars[:]
        try: other_vars.remove(self.key_var)
        except ValueError:
            return { 'data': [], 'layout': dict(title=f"ERROR: '{self.key_var}' parameter must be variable ...")}, [""]

        def name_units(ax_key):
            if ax_key.startswith("param:"):
                _, var, *modifiers = ax_key.split(":")
                if not modifiers:
                    unit = 'n/a'
                else:
                    unit = getattr(Regression, modifiers[-1]).__doc__

                return var.title(), unit
            else:
                return ax_key, TableStats.stats_by_name[ax_key].unit

        x_name, x_unit = name_units(self.x_key)
        y_name, y_unit = name_units(self.y_key)

        for entry in matrix_view.all_records(params, param_lists):
            def value(ax_key):
                if ax_key.startswith("param:"):
                    _, var, *modifiers = ax_key.split(":")
                    val = params[var]
                    for mod in modifiers:
                        val = getattr(Regression, mod)(val)
                    return val
                else:
                    return entry.stats[ax_key].value
            try:
                _x = value(self.x_key)
                _y = value(self.y_key)
            except KeyError:
                print(f"{self.x_key} or {self.y_key} missing values for ", key)
                continue

            legend_key = f"{self.key_var}={params[self.key_var]}"

            reg_key = "all" if not other_vars else \
                 " | ".join(f"{k}={params[k]}" for k in other_vars)

            fixed_params[reg_key] = {k: params[k] for k in other_vars}
            x[reg_key].append(_x)
            y[reg_key].append(_y)
            text[reg_key].append(legend_key)

            reg_x[reg_key].append(_x)
            reg_y[reg_key].append(_y)

        for i, legend_key in enumerate(x.keys()):
            if len(y[legend_key]) < MIN_COUNT_FOR_REGR: continue

            fig.add_trace(go.Scatter(x=x[legend_key], y=y[legend_key], mode='markers', name=legend_key,
                                     hovertext=text[legend_key],hoverinfo="text+x+y", hoverlabel= {'namelength' :-1},
                                     legendgroup=legend_key,
                                     marker=dict(symbol="cross", size=15, color=COLORS(i))))

        x_title = f"{x_name} ({x_unit})"
        y_title = f"{y_name} ({y_unit})"

        fig.update_layout(yaxis=dict(zeroline=True, showgrid=False, rangemode='tozero',
                                     title=y_title),
                          xaxis=dict(title=x_title))

        x_range = None
        formulae = []
        for i, reg_key in enumerate(reg_x.keys()):
            all_x = reg_x[reg_key]
            all_y = reg_y[reg_key]
            if len(all_y) < MIN_COUNT_FOR_REGR: continue
            # https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.linregress.html
            slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(all_x, all_y)

            if math.isnan(slope): continue

            line = slope*np.array(all_x)+intercept
            fig.add_trace(go.Scatter(x=all_x, y=line, mode='lines', hovertext="text",
                                     legendgroup=reg_key,
                                     name=reg_key, line=dict(color=COLORS(i))))

            if not x_range: x_range = [all_x[0], all_x[-1]]
            x_range = [min(x_range[0], min(all_x)), max(x_range[1], max(all_x))]

            def print_float(f):
                from decimal import Decimal
                def fexp(number):
                    (sign, digits, exponent) = Decimal(number).as_tuple()
                    try:
                        return len(digits) + exponent - 1
                    except:
                        import pdb;pdb.set_trace()
                        return "XXX"
                def fman(number):
                    return Decimal(number).scaleb(-fexp(number)).normalize()

                return f"{f:.2f}"
                return f"{fman(f):.2f} * 10^{fexp(f)}"

            PARAMS_REWRITE = {
                #'keyframe-period': lambda x:x,
                #'bitrate': Regression.bitrate_in_mbps,
                'framerate': lambda x:x,
                'resolution': Regression.res_in_mpix,
            }

            fix_equa_params = " ; ".join(f"{k}={float(PARAMS_REWRITE[k](v)):.2f}" \
                                           for k, v in fixed_params[reg_key].items() \
                                           if k in PARAMS_REWRITE)
            coeff = slope
            for k, v in fixed_params[reg_key].items():
                if k not in PARAMS_REWRITE: continue
                coeff /= float(PARAMS_REWRITE[k](v))

            #f" | r={r_value:+.3e}, p={p_value:+.3e}, stdev={std_err:+.3e}"
            x = x_name.lower().replace('guest ', '')
            X = x.upper()[0]
            y = y_name.lower().replace('guest ', '')

            equa_to_solve = f"{y} = {x} * {print_float(slope)} {intercept:+.1f} | {fix_equa_params} |> {coeff:.3f}"

            formulae.append(equa_to_solve)

        fig.update_layout(
            meta=dict(name=self.name, value=formulae),
        )

        fig.update_layout(title=f"{y_name} vs {x_name} | {' x '.join(other_vars)}")

        return fig, list(join(html.Br(), formulae)) #[html.Span(f) for f in formulae]
