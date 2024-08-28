import logging
import math
from collections import defaultdict
import copy

import pandas as pd
import plotly.io as pio
import plotly.express as px
from dash import html

import matrix_benchmarking.plotting.ui.report as plotting_ui_report
import matrix_benchmarking.common as common

from . import analyze

IMPROVED_COLORS_BY_RATING = dict(zip(analyze.IMPROVED_EVALUATION.keys(), ["#CFFDBC", "#77c71a", "#abd216", "#f0f200"]))
IMPROVED_COLORS_BY_EVAL = dict(zip(analyze.IMPROVED_EVALUATION.values(), IMPROVED_COLORS_BY_RATING.values()))

DEGRADED_COLORS_BY_RATING = dict(zip(analyze.DEGRADED_EVALUATION.keys(), ["#CFFDBC", "#a5c90f", "#ffb366", "#ff8829"]))
DEGRADED_COLORS_BY_EVAL = dict(zip(analyze.DEGRADED_EVALUATION.keys(), DEGRADED_COLORS_BY_RATING.values()))

COLOR_OVERALL_NAMES = "#F5F5DC" # beige

COLOR_OVERVIEW_VARIABLE = "#ADD8E6" # Light Blue
COLOR_OVERVIEW_FIX = "#ccf0a2" # Light green

COLOR_STDEV_BOUND = "#32CD32" # Lime Green
COLOR_STDEV_NOT_BOUND = "#FF5733" # Red brick
COLOR_STDEV_NONE = "lightgreen"

COLOR_STDEV_IMPROVED = "#32CD32"
COLOR_STDEV_DEGRADED = "#FF5733"

COLOR_NAN = "white; color: white"
COLOR_DEFAULT = "#CFFDBC"

# Declare properties to style the Table
STYLE_TABLE = [
    {
        'selector': 'tr:hover',
        'props': [
            ('background-color', 'yellow'),
        ]
    },
    {
        'selector': 'th',
        'props': [
            ('background-color', 'grey'),
            ('border-collapse', 'collapse'),
        ]
    },
    {
        'selector': 'td',
        'props': [
            ('border-collapse', 'collapse'),
        ]
    },
    {
        'selector': 'caption',
        'props': [
            ('font-size', '1.875em'),
            ('text-align', 'center'),
        ]
    }
]

STYLE_HIDE_COLUMN_TITLES = [{'selector': 'thead', 'props': [('display', 'none')]}]

def longestCommonPrefix(strs):
    if not strs or len(strs) == 1:
        return ""

    min_s = min(strs)
    max_s = max(strs)
    if not min_s:
        return ""
    for i in range(len(min_s)):
        if max_s[i] != min_s[i]:
            return max_s[:i]
    return min_s[:]


def generate_regression_analyse_report(regression_df, kpi_filter, comparison_key):
    pio.renderers.default = "notebook"

    idx = 0
    total_points = 0
    warnings_already_shown = []
    failures = 0
    improvement_summary_by_all = 0
    degradation_summary_by_all = 0

    report = []

    report.append(html.H1(f"Regression Analysis Summary"))

    summary_html = [] # will be populated after the loop
    report.append(html.Div(summary_html))
    all_regr_results = []

    all_settings = defaultdict(set)
    variables = []
    fix_settings = []

    for row_values in regression_df.values:
        row = dict(zip(regression_df, row_values))
        ref_entry = row["ref"]
        for k, v in ref_entry.results.lts.metadata.settings.__dict__.items():
            if not v.__hash__: continue
            all_settings[k].add(v)

    for lts_meta_key in common.LTS_META_KEYS:
        all_settings.pop(lts_meta_key, None)

    for k, v in all_settings.items():
        if len(v) > 1:
            variables.append(k)
        else:
            fix_settings.append(k)


    for row_values in regression_df.values:
        row = dict(zip(regression_df, row_values))
        ref_entry = row["ref"]
        kpis = ref_entry.results.lts.kpis

        common_prefix = longestCommonPrefix(list(kpis.keys()))
        break

    improvement_summary_by_kpi = defaultdict(int)
    degradation_summary_by_kpi = defaultdict(int)
    for row_values in regression_df.values:
        idx += 1

        logging.info(f"Processing entry # {idx} ...")

        row = dict(zip(regression_df, row_values))
        ref_entry = row["ref"]
        kpis = ref_entry.results.lts.kpis

        metadata = copy.copy(ref_entry.results.lts.metadata)
        del metadata.config
        metadata_settings = metadata.settings

        del metadata.settings

        regression_name = "|".join(f"{k}={metadata_settings.__dict__[k]}" for k in variables)
        if not regression_name:
            regression_name = "Unique test"

        report.append(html.H1(regression_name))
        entry_regr_results = dict(name=f"{regression_name}")

        html_urls = []
        for url_name, url in metadata_settings.urls.items():
            html_urls.append(html.Li(html.A(url_name, href=url)))
        report.append(html.Ul(html_urls))

        lts_settings_df = pd.DataFrame(metadata.__dict__.items())
        lts_settings_html = lts_settings_df.style\
                                   .hide(axis="index")\
                                   .set_table_styles(table_styles=STYLE_TABLE + STYLE_HIDE_COLUMN_TITLES)

        report.append(html.H3("Settings"))
        report.append(lts_settings_html)

        kpi_settings_df = pd.DataFrame(metadata_settings.__dict__.items())
        kpi_settings_html = kpi_settings_df.style\
                                   .hide(axis="index")\


        report.append(html.H3("Labels"))
        report.append(kpi_settings_html)

        improvement_summary_by_entry = 0
        degradation_summary_by_entry = 0
        for kpi in kpis:
            if kpi_filter and kpi_filter not in kpi:
                continue

            ref_kpi = ref_entry.results.lts.kpis[kpi]
            if isinstance(ref_kpi.value, list): continue
            report.append(html.H2(f" KPI {kpi}"))

            ref_name = getattr(ref_kpi, comparison_key)

            comparison_data = []

            comparison_data.append({comparison_key: f"{ref_name} (ref)", "value": ref_kpi.value})
            historical_values = []

            for comparison_key_value in sorted(row.keys()):
                if comparison_key_value == "ref": continue

                comparison_gathered_entries = row[comparison_key_value]
                if isinstance(comparison_gathered_entries, float) and math.isnan(comparison_gathered_entries):
                    continue

                entry = comparison_gathered_entries.results[0]

                entry_name = getattr(entry.results.metadata.settings, comparison_key)

                records_count = len(comparison_gathered_entries.results)
                if records_count != 1:
                    msg = f"Multiple records ({records_count}) found for {entry_name}. Taking the first one."
                    if msg not in warnings_already_shown:
                        warnings_already_shown.append(msg)
                        logging.warning(msg)

                kpi_value = entry.results.kpis.__dict__[kpi].value

                comparison_data.append({comparison_key: entry_name, "value": kpi_value})
                historical_values.append(kpi_value)

            comparison_df = pd.DataFrame(comparison_data)

            from distutils.version import LooseVersion

            comparison_df["__sort_index__"] = comparison_df[comparison_key].apply(LooseVersion)
            comparison_df = comparison_df.sort_values(by=["__sort_index__"]).drop("__sort_index__", axis=1)

            comparison_format = dict(
                value="{:.2f} "+ref_kpi.unit,
            )
            comparison_df_html = comparison_df.style\
                                              .format(comparison_format)\
                                              .hide(axis="index")\
                                              .set_table_styles(table_styles=STYLE_TABLE)

            report.append(comparison_df_html)
            lower_better = getattr(ref_kpi, "lower_better", None)

            if lower_better is None:
                msg = f"KPI '{kpi}' does not define the 'lower_better' property :/ "
                if msg not in warnings_already_shown:
                    logging.warning(msg)
                    warnings_already_shown.append(msg)

            regr_result = analyze.do_regression_analyze(ref_kpi.value, historical_values, lower_better=lower_better)
            if regr_result["improved"]:
                improvement_summary_by_entry += regr_result["rating"]
                improvement_summary_by_kpi[kpi] += regr_result["rating"]
                improvement_summary_by_all += regr_result["rating"]
            else:
                degradation_summary_by_entry += regr_result["rating"]
                degradation_summary_by_kpi[kpi] += regr_result["rating"]
                degradation_summary_by_all += regr_result["rating"]

            entry_regr_results[kpi.replace(common_prefix, "")] = "{} • {}".format(regr_result["rating"], regr_result["evaluation"])

            regr_df = pd.DataFrame([regr_result])

            regr_format = dict(
                current_value="{:.2f} "+ref_kpi.unit,
                previous_mean="{:.1f} "+ref_kpi.unit,
                std_dev="{:.1f}",
                std_dev_1="{:.1f} %",
                std_dev_2="{:.1f} %",
                std_dev_3="{:.1f} %",
                change="{:.1f} %",
                delta="{:.1f}"
            )

            def conditional_format(row):
                fmt = []
                for key, value in zip(row.keys(), row.values):
                    style = ""
                    rating_colors = IMPROVED_COLORS_BY_RATING if row["improved"] else DEGRADED_COLORS_BY_RATING
                    evaluation = analyze.IMPROVED_EVALUATION if row["improved"] else analyze.DEGRADED_EVALUATION
                    if key in ["std_dev_1_bound", "std_dev_2_bound", "std_dev_3_bound"]:
                        if value is True:
                            style = f"background: {COLOR_STDEV_BOUND}"  # green
                        elif value is False:
                            style = f"background: {COLOR_STDEV_NOT_BOUND}"  # red
                        elif value is None:
                            style = f"background: {COLOR_STDEV_NONE}"

                    if key == "improved":
                        style = f"background: {COLOR_STDEV_IMPROVED}" if value \
                            else f"background: {COLOR_STDEV_DEGRADED}"

                    if key == "rating":
                        color = rating_colors[row["rating"]]
                        style = f"background: {color}"

                    if key == "evaluation":
                        color = rating_colors[row["rating"]]
                        style = f"background: {color}"

                    fmt.append(style)

                return fmt

            regr_df_html = regr_df.style\
                                  .apply(conditional_format, axis = 1)\
                                  .format(regr_format)\
                                  .hide(axis="index")\
                                  .set_table_styles(table_styles=STYLE_TABLE)

            report.append(regr_df_html)

            INCLUDE_FIG = False
            if INCLUDE_FIG:
                fig = px.line(df, x=comparison_key, y="value",
                              markers=True,
                              title=f"{ref_kpi.help} (in {ref_kpi.unit})",
                              )

                # not using dcc.Graph() here, so this will follow another path than plots in plotting reports.
                # here, fig.to_html() will be called.
                report.append(html.Div([fig], style=dict(height="525px", width="100%")))

            total_points += 1
            if not regr_result["improved"] and regr_result["rating"] == 4:
                failures += 1

        entry_regr_results["overall improvement"] = f"{improvement_summary_by_entry / (len(entry_regr_results) - 1):.2f}" if improvement_summary_by_entry else "nan"
        entry_regr_results["overall degradation"] = f"{degradation_summary_by_entry / (len(entry_regr_results) - 1):.2f}" if degradation_summary_by_entry else "nan"
        all_regr_results.append(entry_regr_results)

        def all_regr_results_conditional_format(row):
            fmt = []

            def overall_row(degraded):
                rating_colors = (DEGRADED_COLORS_BY_RATING if degraded else IMPROVED_COLORS_BY_RATING)

                overall_fmt = [f"background: {COLOR_OVERALL_NAMES}"]
                for _rating in row.values[1:]:
                    if math.isnan(float(_rating)):
                        color = COLOR_NAN
                    else:
                        color = rating_colors.get(int(float(_rating)), COLOR_DEFAULT)
                    overall_fmt.append(f"background: {color}")


                overall_fmt[-1 if degraded else -2] += "; border: 3px solid black;"
                overall_fmt[-2 if degraded else -1] += "; color: white;"
                return overall_fmt

            for key, value in zip(row.keys(), row.values):
                if row["name"] == "overall degradation":
                    return overall_row(degraded=True)
                if row["name"] == "overall improvement":
                    return overall_row(degraded=False)

                if key == "name":
                    style = f"background: {COLOR_OVERALL_NAMES}"
                elif key == "overall degradation":
                    color = DEGRADED_COLORS_BY_RATING.get(int(float(value)), COLOR_DEFAULT)  if value != "nan" else COLOR_NAN
                    style = f"background: {color}"
                elif key == "overall improvement":
                    color = IMPROVED_COLORS_BY_RATING.get(int(float(value)), COLOR_DEFAULT) if value != "nan" else COLOR_NAN
                    style = f"background: {color}"
                else:
                    rating = int(value.split()[0])
                    degraded = value.split()[-1] in analyze.DEGRADED_EVALUATION.values()
                    color = (DEGRADED_COLORS_BY_RATING if degraded else IMPROVED_COLORS_BY_RATING)[rating]
                    style = f"background: {color}"

                fmt.append(style)

            return fmt


    summary_html.append(html.H2("Configuration overview"))

    config_overview_data = []
    for k, v in all_settings.items():
        val = ", ".join(map(str, sorted(v)))
        config_overview_data.append(dict(name=k, value=val))

    def config_overview_conditional_format(row):
        color = COLOR_OVERVIEW_VARIABLE if row["name"] in variables \
            else COLOR_OVERVIEW_FIX

        return [f"background: {color}"] * len(row)

    config_overview_df = pd.DataFrame(config_overview_data)
    config_overview_df_html = config_overview_df\
        .style\
        .apply(config_overview_conditional_format, axis = 1)\
        .hide(axis="index")\
        .set_table_styles(table_styles=STYLE_TABLE)
    summary_html.append(config_overview_df_html)

    summary_html.append(html.H2("Results overview"))

    kpi_overall_degradation_data = dict(name="overall degradation")
    kpi_overall_improvement_data = dict(name="overall improvement")
    overall_improvement_total = 0
    overall_degradation_total = 0

    for k, improve in improvement_summary_by_kpi.items():
        improve_value = improve/idx
        overall_improvement_total += improve_value
        kpi_overall_improvement_data[k.replace(common_prefix, "")] = f"{improve_value:.2f}"

    for k, degrade in degradation_summary_by_kpi.items():
        degrade_value = degrade/idx
        overall_degradation_total += degrade_value
        kpi_overall_degradation_data[k.replace(common_prefix, "")] = f"{degrade_value:.2f}"

    overall_improvement_rating = overall_improvement_total / len(improvement_summary_by_kpi) if improvement_summary_by_kpi else 0
    overall_degradation_rating = overall_degradation_total / len(degradation_summary_by_kpi) if degradation_summary_by_kpi else 0

    kpi_overall_degradation_data["overall degradation"] = f"{overall_degradation_rating:.2f}"
    kpi_overall_improvement_data["overall improvement"] = f"{overall_improvement_rating:.2f}"

    all_regr_results_df = pd.DataFrame(all_regr_results + [kpi_overall_degradation_data, kpi_overall_improvement_data])

    all_regr_results_df_html = all_regr_results_df\
        .style\
        .apply(all_regr_results_conditional_format, axis = 1)\
        .hide(axis="index")\
        .set_table_styles(table_styles=STYLE_TABLE)
    summary_html.append(all_regr_results_df_html)

    summary = f"Performed {total_points} regression analyses over {idx} entries. {failures} didn't pass."
    logging.info(summary)
    summary_html.append(html.P(html.B(summary)))

    return html.Span(report), failures


def generate_and_save_regression_analyse_report(dest, regression_df, kpi_filter, comparison_key):
    report, failures = generate_regression_analyse_report(regression_df, kpi_filter, comparison_key)

    if dest is None:
        logging.warning("Skipping report generation.")
        return failures

    plotting_ui_report.generate(None, dest, report, None, include_header=False)

    return failures
