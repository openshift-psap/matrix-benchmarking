
import logging
import math
from collections import defaultdict
import copy
from packaging.version import Version

import pandas as pd
import plotly
import plotly.io as pio
import plotly.express as px
from dash import html

import matrix_benchmarking.plotting.ui.report as plotting_ui_report
import matrix_benchmarking.common as common

COLOR_OVERALL_NAMES = "#F5F5DC" # beige

import matrix_benchmarking.analyze as analyze

COLOR_IMPROVED = "#32CD32"
COLOR_DEGRADED = "#FF5733"
COLOR_IMPROVED_NONE = "#ADD8E6"

COLOR_NAN = "white; color: white"
COLOR_DEFAULT = "#CFFDBC"

def is_nan(entry):
    return isinstance(entry, float) and math.isnan(entry)

def get_rating_color(rating, improved=True):
    if is_nan(rating):
        return COLOR_NAN

    GREEN = "#00FF80"
    WHITE = "#FFFFFF"
    RED = "#FF6666"

    DARK_GREEN = "#06402b"
    DARK_RED = "#8B0000"

    if rating is None:
        return WHITE

    if rating >= 1:
        return DARK_GREEN if improved else DARK_RED

    # see also plotly.colors.sequential.Inferno_r and others
    if improved:
        color_scale = [WHITE, GREEN]
    else:
        color_scale = [WHITE, RED]

    color = plotly.colors.sample_colorscale(
        color_scale, samplepoints=[rating])[0]

    return color

COLOR_OVERVIEW_VARIABLE = "#ADD8E6" # Light Blue
COLOR_OVERVIEW_FIX = "#ccf0a2" # Light green

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


class OvervallResult():
    def __init__(self, rating, evaluation, improved):
        self.rating = rating
        self.evaluation = evaluation
        self.improved = improved

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


def generate_regression_analyse_report(regression_df, kpi_filter, comparison_keys, ignored_keys):
    pio.renderers.default = "notebook"

    idx = 0
    total_points = 0
    warnings_already_shown = []
    failures = 0
    not_analyzed = 0
    no_history = 0

    improvement_summary_by_all = 0
    degradation_summary_by_all = 0

    report = []

    report.append(html.H1(f"Regression Analysis Summary"))

    summary_html = [] # will be populated after the loop
    report.append(html.Div(summary_html))
    all_regr_results = []

    all_lts_settings = defaultdict(set)
    all_settings = defaultdict(set)
    variables = []
    fix_settings = []
    lts_variables = []
    lts_fix_settings = []

    for row_values in regression_df.values:
        row = dict(zip(regression_df, row_values))

        for row_key, entry in zip(regression_df, row_values):
            if is_nan(entry): continue
            if row_key == "ref": continue

            dest_all_settings = all_settings if row_key == row["ref"] else all_lts_settings

            entry_settings = entry.results.lts.metadata.settings if row_key == row["ref"] \
                else entry.results[0].results.metadata.settings

            for k, v in entry_settings.__dict__.items():
                if not v.__hash__: continue
                if k in ignored_keys: continue
                dest_all_settings[k].add(v)

    for lts_meta_key in common.LTS_META_KEYS:
        all_settings.pop(lts_meta_key, None)
        all_lts_settings.pop(lts_meta_key, None)

    for k, v in all_settings.items():
        (variables if len(v) > 1 else fix_settings).append(k)

    variables.sort()

    for k, v in all_lts_settings.items():
        (lts_variables if len(v) > 1 else lts_fix_settings).append(k)

    for row_values in regression_df.values:
        row = dict(zip(regression_df, row_values))
        ref_entry = row[row["ref"]]
        kpis = ref_entry.results.lts.kpis

        kpis_common_prefix = longestCommonPrefix(list(kpis.keys()))
        break

    improvement_summary_by_kpi = defaultdict(int)
    degradation_summary_by_kpi = defaultdict(int)
    for row_values in regression_df.values:
        idx += 1

        logging.info(f"Processing entry # {idx} ...")

        row = dict(zip(regression_df, row_values))

        ref_entry = row[row["ref"]]
        kpis = ref_entry.results.lts.kpis

        metadata = copy.copy(ref_entry.results.lts.metadata)
        metadata_settings = copy.copy(metadata.__dict__.pop("settings"))

        regression_name = "|".join(f"{k}={metadata_settings.__dict__[k]}" for k in variables)
        if not regression_name:
            regression_name = "Unique test"

        report.append(html.H1(regression_name))

        # entry header

        report += _generate_entry_header(metadata_settings, metadata)

        if len([... for c in row.values() if not is_nan(c)]) == 1:
            report.append(html.P(html.B("No historical records ...")))
            no_history += 1
            continue

        entry_regr_results = dict()
        for var in variables:
            entry_regr_results[var] = metadata_settings.__dict__[var]
        if not variables:
            entry_regr_results["name"] = regression_name

        improvement_summary_by_entry = 0
        degradation_summary_by_entry = 0

        for kpi in kpis:
            if kpi_filter and kpi_filter not in kpi:
                continue

            ref_kpi = ref_entry.results.lts.kpis[kpi]
            if isinstance(ref_kpi.value, list): continue
            report.append(html.H2(f" KPI {kpi}"))

            ref_name = row["ref"]

            comparison_data = []

            ref_line = dict()
            for k in comparison_keys:
                ref_line[k] = ref_kpi.__dict__.get(k)

            # keep this vvv below ^^^ to preserve the order in the rendered table
            ref_line["value"] = ref_kpi.value
            ref_line["ref"] = "*"
            comparison_data.append(ref_line)

            historical_values = []

            for comparison_key_value in sorted(row.keys()):
                if comparison_key_value == "ref": continue

                comparison_gathered_entries = row[comparison_key_value]
                if is_nan(comparison_gathered_entries):
                    continue
                if comparison_key_value == row["ref"]:
                    continue

                entry = comparison_gathered_entries.results[0]

                entry_name = {k: entry.results.metadata.settings.__dict__[k] for k in comparison_keys}

                records_count = len(comparison_gathered_entries.results)
                if records_count != 1:
                    msg = f"Multiple records ({records_count}) found for {entry_name}. Taking the first one."
                    if msg not in warnings_already_shown:
                        warnings_already_shown.append(msg)
                        logging.warning(msg)

                kpi_value = entry.results.kpis.__dict__[kpi].value
                history_line = dict(ref="", value=kpi_value)
                comparison_data.append(history_line | entry_name)
                historical_values.append(kpi_value)

            # Comparison table

            report.append(_generate_comparison_table(comparison_data, comparison_keys, ref_kpi.unit))

            lower_better = getattr(ref_kpi, "lower_better", None)

            if lower_better is None:
                msg = f"KPI '{kpi}' does not define the 'lower_better' property :/ "
                if msg not in warnings_already_shown:
                    logging.warning(msg)
                    warnings_already_shown.append(msg)

            regr_result = analyze.do_regression_analyze(ref_kpi.value, historical_values, lower_better=lower_better, kpi_unit=ref_kpi.unit)

            validate_regression_result(regr_result)

            if regr_result.rating is not None:
                if regr_result.improved:
                    improvement_summary_by_entry += regr_result.rating
                    improvement_summary_by_kpi[kpi] += regr_result.rating
                    improvement_summary_by_all += regr_result.rating
                else:
                    degradation_summary_by_entry += regr_result.rating
                    degradation_summary_by_kpi[kpi] += regr_result.rating
                    degradation_summary_by_all += regr_result.rating

            entry_regr_results[kpi.replace(kpis_common_prefix, "")] = OvervallResult(regr_result.rating, regr_result.evaluation, regr_result.improved)

            # Evaluation results

            report.append(html.H3("Evaluation results"))
            report.append(_generate_evaluation_results(regr_result))

            # Details

            report.append(html.H3("Details"))
            details_data = [regr_result.details] if isinstance(regr_result.details, dict) else regr_result.details
            regr_df_html = pd.DataFrame(details_data).style\
                                                              .apply(regr_result.details_conditional_fmt, axis = 1)\
                                                              .format(regr_result.details_fmt)\
                                                              .hide(axis="index")\
                                                              .set_table_styles(table_styles=STYLE_TABLE)

            report.append(regr_df_html)

            INCLUDE_FIG = False
            if INCLUDE_FIG:
                # deprecated. Needs to be rewritten with multiple comparison_keys
                fig = px.line(df, x=comparison_key, y="value",
                              markers=True,
                              title=f"{ref_kpi.help} (in {ref_kpi.unit})",
                              )

                # not using dcc.Graph() here, so this will follow another path than plots in plotting reports.
                # here, fig.to_html() will be called.
                report.append(html.Div([fig], style=dict(height="525px", width="100%")))

            total_points += 1
            if regr_result.accepted is False:
                failures += 1
            elif regr_result.accepted is None:
                not_analyzed += 1

        entry_regr_results["overall improvement"] = OvervallResult(improvement_summary_by_entry / len(entry_regr_results), None, True) if entry_regr_results else None
        entry_regr_results["overall degradation"] = OvervallResult(degradation_summary_by_entry / len(entry_regr_results), None, False) if entry_regr_results else None
        all_regr_results.append(entry_regr_results)

    # Configuration overview

    summary_html.append(html.H2("Configuration overview"))
    summary_html.append(_generate_configuration_overview(all_settings, variables))

    # LTS overview
    summary_html.append(html.H2("Historical records overview"))
    summary_html.append(_generate_lts_overview(all_lts_settings, lts_variables))

    # Results overview

    summary_html.append(html.H2("Results overview"))
    summary_html.append(_generate_results_overview(all_regr_results, variables, improvement_summary_by_kpi, degradation_summary_by_kpi, kpis_common_prefix))

    # Summary

    summary = f"Performed {total_points} regression analyses over {idx} entries. {failures} didn't pass."
    if no_history:
        summary += f" {no_history} didn't have historical records."
    if not_analyzed:
        summary += f" {not_analyzed} couldn't be analyzed. "

    logging.info(summary)
    summary_html.append(html.P(html.B(summary)))

    return html.Span(report), failures


def generate_and_save_regression_analyse_report(dest, regression_df, kpi_filter, comparison_key, ignored_keys):
    report, failures = generate_regression_analyse_report(regression_df, kpi_filter, comparison_key, ignored_keys)

    if dest is None:
        logging.warning("Skipping report generation.")
        return failures

    plotting_ui_report.generate(None, dest, report, None, include_header=False)

    return failures


def _generate_entry_header(metadata_settings, metadata):
    header = []

    # --- URLs ---

    if hasattr(metadata_settings, "urls") or hasattr(metadata, "urls"):
        urls = metadata_settings.urls if hasattr(metadata_settings, "urls") else metadata.urls
        html_urls = []
        for url_name, url in urls.items():
            html_urls.append(html.Li(html.A(url_name, href=url)))
        header.append(html.Ul(html_urls))


    # --- LTS Metadata ---

    header.append(html.H3("Settings"))

    metadata.__dict__.pop("urls", None)
    metadata.__dict__.pop("test_path", None)
    metadata.__dict__.pop("run_id", None)
    metadata.__dict__.pop("config", None)

    lts_metadata_df = pd.DataFrame(metadata.__dict__.items())
    lts_metadata_html = lts_metadata_df.style\
                               .hide(axis="index")\
                               .set_table_styles(table_styles=STYLE_TABLE + STYLE_HIDE_COLUMN_TITLES)

    header.append(lts_metadata_html)

    # --- KPI Labels/Settings ---

    header.append(html.H3("Labels"))

    metadata_settings.__dict__.pop("urls", None)
    metadata_settings.__dict__.pop("test_path", None)
    metadata_settings.__dict__.pop("run_id", None)

    kpi_settings_df = pd.DataFrame(metadata_settings.__dict__.items())

    kpi_settings_html = kpi_settings_df.style\
                               .hide(axis="index")\
                               .set_table_styles(table_styles=STYLE_TABLE + STYLE_HIDE_COLUMN_TITLES)

    header.append(kpi_settings_html)

    return header

def _generate_comparison_table(comparison_data, comparison_keys, kpi_unit):
    comparison_df = pd.DataFrame(comparison_data)

    def create_sort_index(_row):
        sort_index = []

        for comparison_key in comparison_keys:
            sort_index += [_row[comparison_key]]

        return Version("+".join(sort_index))

    comparison_df["__sort_index"] = comparison_df.apply(create_sort_index, axis=1)

    comparison_df = comparison_df.sort_values("__sort_index").drop("__sort_index", axis=1)

    comparison_format = dict(value="{:.2f} "+kpi_unit,)

    comparison_df_html = comparison_df.style\
                                      .format(comparison_format)\
                                      .hide(axis="index")\
                                      .set_table_styles(table_styles=STYLE_TABLE)

    return comparison_df_html


def _generate_evaluation_results(regr_result):
    def rating_fmt(value):
        if value is None:
            return "---"

        return f"{value*100:.0f}%"

    regr_results_evaluation_fmt = dict(
        rating = rating_fmt
    )

    def regr_results_evaluation_style(row):
        fmt = []
        for key, value in zip(row.keys(), row.values):
            if key in ("improved", "accepted"):
                color = (COLOR_IMPROVED if value else COLOR_DEGRADED) \
                    if value is not None \
                       else COLOR_IMPROVED_NONE

            if key in ("rating", "evaluation"):
                color = row.rating_color

            style = f"background: {color}"
            fmt.append(style)

        return fmt

    rating_color = get_rating_color(regr_result.rating, regr_result.improved)
    regr_df_html = pd.DataFrame([dict(
        improved=regr_result.improved,
        rating=regr_result.rating,
        rating_color=rating_color,
        evaluation=regr_result.evaluation,
        accepted=regr_result.accepted,
    )]).style\
                     .format(regr_results_evaluation_fmt)\
                     .apply(regr_results_evaluation_style, axis=1)\
                     .hide(["rating_color"], axis=1)\
                     .hide(axis="index")\
                     .set_table_styles(table_styles=STYLE_TABLE)

    return regr_df_html


def _generate_lts_overview(all_lts_settings, lts_variables):
    lts_config_overview_data = []
    for k, v in all_lts_settings.items():
        val = ", ".join(map(str, sorted(v)))
        lts_config_overview_data.append(dict(name=k, value=val))

    def lts_config_overview_conditional_format(row):
        color = COLOR_OVERVIEW_VARIABLE if row["name"] in lts_variables \
            else COLOR_OVERVIEW_FIX

        return [f"background: {color}"] * len(row)

    lts_config_overview_df = pd.DataFrame(lts_config_overview_data)
    lts_config_overview_df_html = lts_config_overview_df\
        .style\
        .apply(lts_config_overview_conditional_format, axis = 1)\
        .hide(axis="index")\
        .set_table_styles(table_styles=STYLE_TABLE)

    return lts_config_overview_df_html


def _generate_configuration_overview(all_settings, variables):
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

    return config_overview_df_html


def _generate_results_overview(all_regr_results, variables, improvement_summary_by_kpi, degradation_summary_by_kpi, kpis_common_prefix):
    entry_count = len(all_regr_results)
    first_column_name = variables[0] if variables else "name"
    kpi_overall_degradation_data = {first_column_name: "overall degradation"} | {k:"" for k in variables[1:]}
    kpi_overall_improvement_data = {first_column_name: "overall improvement"} | {k:"" for k in variables[1:]}
    overall_improvement_total = 0
    overall_degradation_total = 0

    kpi_names = set()

    for k, improve in improvement_summary_by_kpi.items():
        kpi_name = k.replace(kpis_common_prefix, "")
        improve_value = improve/entry_count
        overall_improvement_total += improve_value
        kpi_overall_improvement_data[kpi_name] = OvervallResult(improve_value, None, True)
        kpi_names.add(kpi_name)

    for k, degrade in degradation_summary_by_kpi.items():
        kpi_name = k.replace(kpis_common_prefix, "")
        degrade_value = degrade/entry_count
        overall_degradation_total += degrade_value
        kpi_overall_degradation_data[kpi_name] = OvervallResult(degrade_value, None, False)
        kpi_names.add(kpi_name)

    overall_improvement_rating = overall_improvement_total / len(improvement_summary_by_kpi) if improvement_summary_by_kpi else 0
    overall_degradation_rating = overall_degradation_total / len(degradation_summary_by_kpi) if degradation_summary_by_kpi else 0

    kpi_overall_degradation_data["overall degradation"] = OvervallResult(overall_degradation_rating, None, False)
    kpi_overall_improvement_data["overall improvement"] = OvervallResult(overall_improvement_rating, None, True)

    all_regr_results_df = pd.DataFrame(all_regr_results + [kpi_overall_degradation_data, kpi_overall_improvement_data])

    def fmt(value):
        if is_nan(value):
            return ""

        rating_str = f"{100*value.rating:.0f}%" if isinstance(value.rating, float) \
            else str(value.rating)

        if value.rating is None:
            return value.evaluation

        if value.evaluation is None:
            return rating_str

        return f"{rating_str} • {value.evaluation}"

    overview_fmt = {k: fmt for k in kpi_names | set(["overall improvement", "overall degradation"])}

    all_regr_results_df_html = all_regr_results_df\
        .style\
        .apply(get_all_regr_results_conditional_format(first_column_name, variables), axis = 1)\
        .format(overview_fmt)\
        .hide(axis="index")\
        .set_table_styles(table_styles=STYLE_TABLE)

    return all_regr_results_df_html


def get_all_regr_results_conditional_format(first_column_name, variables):
    def all_regr_results_conditional_format(row):
        fmt = []

        def overall_row(improved):
            names_length = len(variables) or 1

            overall_fmt = [f"background: {COLOR_OVERALL_NAMES}; font-weight: bold;"] * names_length
            for overall_value in row.values[names_length:]:
                color = get_rating_color(overall_value.rating, improved) \
                    if not is_nan(overall_value) else COLOR_NAN

                overall_fmt.append(f"background: {color}")

            overall_fmt[-1 if improved else -2] += "; border: 3px solid black;"
            overall_fmt[-2 if improved else -1] += "; color: white;"

            return overall_fmt


        for key, value in zip(row.keys(), row.values):
            if row[first_column_name] == "overall degradation":
                return overall_row(improved=True)
            if row[first_column_name] == "overall improvement":
                return overall_row(improved=False)

            if key in variables or key == "name":
                style = f"background: {COLOR_OVERALL_NAMES}"
            elif key == "overall degradation":
                color = get_rating_color(value.rating, value.improved)
                style = f"background: {color}"

            elif key == "overall improvement":
                color = get_rating_color(value.rating, value.improved)

                style = f"background: {color}"
            else:
                # KPI result
                if is_nan(value):
                    style = "background: red"
                else:
                    color = get_rating_color(value.rating,  value.improved)
                    style = f"background: {color}"

            fmt.append(style)

        return fmt

    return all_regr_results_conditional_format


def validate_regression_result(regr_result):
    if regr_result is None:
        raise ValueError("The regr_result is None ...")

    if regr_result.accepted is None:
        return

    if "inf" in str(regr_result.rating):
        raise ValueError(f"The regr_result rating shouldn't be infinite ...")

    if regr_result.rating < 0:
        raise ValueError(f"The regr_result rating ({regr_result.rating:.2f}) should not be negative")

    range_0_1 = (0 <= regr_result.rating < 1)
    if not ((regr_result.accepted and range_0_1)
            or (not regr_result.accepted and not range_0_1)):

        if not regr_result.improved:
            raise ValueError(f"The regr_result rating ({regr_result.rating:.2f}) should be between 0 and 1 only when the value is accepted ({regr_result.accepted})...")
