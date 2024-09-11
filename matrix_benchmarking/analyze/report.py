
import logging
import math
from collections import defaultdict
import copy
from packaging.version import Version, InvalidVersion

import pandas as pd
import plotly
import plotly.io as pio
import plotly.express as px
from dash import html

import matrix_benchmarking.plotting.ui.report as plotting_ui_report
import matrix_benchmarking.common as common

import matrix_benchmarking.analyze as analyze

# if false, skip the entries without regression in the report
INCLUDE_ALL_THE_ENTRIES = True
# if false, skip the KPIs without regression in the report
INCLUDE_ALL_THE_KPIS = True
# if false, do not include the regression plots (~4.5MB per plot)
INCLUDE_REGRESSION_PLOT = False

COLOR_OVERVIEW_NAMES = "#F5F5DC" # beige

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

    OVERVIEW_IMPROVED = "#61c45a"
    OVERVIEW_REGRESSED = "#ff7f00"
    OVERVIEW_STABLE = "#e8fedd"

    if rating is None:
        return OVERVIEW_STABLE

    if rating >= 1:
        return OVERVIEW_IMPROVED if improved else OVERVIEW_REGRESSED

    # see also plotly.colors.sequential.Inferno_r and others
    if improved:
        color_scale = [OVERVIEW_STABLE, OVERVIEW_IMPROVED]
    else:
        color_scale = [OVERVIEW_STABLE, OVERVIEW_REGRESSED]

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
    def __init__(self, rating, description, improved, current_value_str):
        self.rating = rating
        self.description = description
        self.improved = improved
        self.current_value_str = current_value_str

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


def generate_regression_analyse_report(regression_df, kpi_filter, comparison_keys, ignored_keys, sorting_keys):
    pio.renderers.default = "notebook"

    idx = 0
    total_points = 0
    warnings_already_shown = []
    failures = 0
    not_analyzed = 0
    no_history = 0
    significant_performance_increase = 0

    report = []
    report.append(html.H1(f"Regression Analysis Summary"))

    summary_html = [] # will be populated after the loop
    report.append(html.Div(summary_html))
    all_regr_results_data = []

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
    # take the sorting keys in the reversed order,
    # so that sorting_keys[0] ends up in variables[0], etc
    for key in sorting_keys[::-1]:
        if key not in variables: continue
        # move the key first
        variables.remove(key)
        variables.insert(0, key)

    for k, v in all_lts_settings.items():
        (lts_variables if len(v) > 1 else lts_fix_settings).append(k)

    for row_values in regression_df.values:
        row = dict(zip(regression_df, row_values))
        ref_entry = row[row["ref"]]
        kpis = ref_entry.results.lts.kpis

        kpis_common_prefix = longestCommonPrefix(list(kpis.keys()))
        break

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

        entry_report = []
        entry_report.append(html.H1(["Entry #", idx, " – ", regression_name]))

        # entry header

        entry_report += _generate_entry_header(metadata_settings, metadata)

        if len([... for c in row.values() if not is_nan(c)]) == 1:
            report.append(html.P(html.B("No historical records ...")))
            no_history += 1
            continue

        entry_regr_results = dict(entry_id=idx)
        for var in variables:
            entry_regr_results[var] = metadata_settings.__dict__[var]
        if not variables:
            entry_regr_results["name"] = regression_name

        include_this_entry_in_report = False

        for kpi in kpis:
            if kpi_filter and kpi_filter not in kpi:
                continue

            ref_kpi = ref_entry.results.lts.kpis[kpi]
            if isinstance(ref_kpi.value, list): continue

            if ref_kpi.ignored_for_regression:
                continue

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

            lower_better = getattr(ref_kpi, "lower_better", None)

            if lower_better is None:
                msg = f"KPI '{kpi}' does not define the 'lower_better' property :/ "
                if msg not in warnings_already_shown:
                    logging.warning(msg)
                    warnings_already_shown.append(msg)

            regr_result = analyze.do_regression_analyze(ref_kpi.value, historical_values, lower_better=lower_better, kpi_unit=ref_kpi.unit)

            validate_regression_result(regr_result)

            if ref_kpi.full_format:
                current_value_str = ref_kpi.full_format(ref_kpi)
            elif ref_kpi.format:
                if ref_kpi.divisor:
                    current_value_str = ref_kpi.format.format(ref_kpi.value / ref_kpi.divisor) + f" {ref_kpi.divisor_unit}"
                else:
                    current_value_str = ref_kpi.format.format(ref_kpi.value) + f" {ref_kpi.unit}"
            else:
                current_value_str = f"{ref_kpi.value:.0f} {ref_kpi.unit}"

            entry_regr_results[kpi.replace(kpis_common_prefix, "")] = \
                OvervallResult(
                    regr_result.rating,
                    regr_result.description,
                    regr_result.improved,
                    current_value_str=current_value_str)

            include_this_kpi_in_report = False
            total_points += 1
            if regr_result.accepted is False:
                failures += 1
                include_this_kpi_in_report = True
            elif regr_result.accepted is None:
                not_analyzed += 1
            elif regr_result.improved and regr_result.rating > 1:
                significant_performance_increase += 1
                include_this_kpi_in_report = True


            if include_this_kpi_in_report:
                include_this_entry_in_report = True

            if INCLUDE_ALL_THE_ENTRIES:
                include_this_entry_in_report = True
                include_this_kpi_in_report = True

            if not include_this_kpi_in_report: continue

            comparison_df = _generate_sorted_pd_table(comparison_data, comparison_keys)

            # KPI header

            entry_report.append(html.H2(f"Entry #{idx} KPI {kpi}"))
            entry_report.append(_generate_comparison_table(comparison_df, ref_kpi.unit))

            # Evaluation results

            entry_report.append(html.H3("Evaluation results"))
            entry_report.append(_generate_evaluation_results(regr_result))

            # Details

            entry_report.append(html.H3("Details"))
            entry_report.append(_generate_details_table(regr_result))

            # Plot
            if INCLUDE_REGRESSION_PLOT:
                entry_report.append(_generate_comparison_plot(comparison_df, comparison_keys,
                                                              kpi, ref_kpi, kpis_common_prefix))


        if not include_this_entry_in_report: continue

        report += entry_report
        all_regr_results_data.append(entry_regr_results)

    # Configuration overview

    summary_html.append(html.H2("Configuration overview"))
    summary_html.append(_generate_configuration_overview(all_settings, variables))

    # LTS overview
    summary_html.append(html.H2("Historical records overview"))
    summary_html.append(_generate_lts_overview(all_lts_settings, lts_variables))

    # Results overview

    summary_html.append(html.H2("Results overview"))
    summary_html.append(_generate_results_overview(all_regr_results_data, variables,  kpis_common_prefix))

    # Summary

    summary = f"Performed {total_points} regression analyses over {idx} entries. {failures} didn't pass."
    if no_history:
        summary += f" {no_history} didn't have historical records."
    if not_analyzed:
        summary += f" {not_analyzed} couldn't be analyzed. "
    if significant_performance_increase:
        summary += f" {significant_performance_increase} significant performance increases. "

    logging.info(summary)
    summary_html.append(html.P(html.B(summary)))

    return html.Span(report), failures


def generate_and_save_regression_analyse_report(dest, regression_df, kpi_filter, comparison_key, ignored_keys, sorting_keys):
    report, failures = generate_regression_analyse_report(regression_df, kpi_filter, comparison_key, ignored_keys, sorting_keys)

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

def _generate_sorted_pd_table(comparison_data, comparison_keys):
    comparison_df = pd.DataFrame(comparison_data)

    def to_version(value):
        try:
            return Version(str(value))
        except InvalidVersion:
            pass
        safe_value = "1+" + value.replace("/", ".").replace(":", ".")
        try:
            return Version(safe_value)
        except InvalidVersion:
            logging.warning(f"Cannot parse '{value}' as a version :/")
            return Version("1.0") # ordering will be wrong

    def create_sort_index(_row):
        sort_index = []

        for comparison_key in comparison_keys:
            sort_index += [to_version(_row[comparison_key])]

        return sort_index

    comparison_df["__sort_index"] = comparison_df.apply(create_sort_index, axis=1)

    return comparison_df.sort_values("__sort_index").drop("__sort_index", axis=1)


def _generate_comparison_table(comparison_df, kpi_unit):
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

            if key in ("rating", "description"):
                color = row.rating_color

            style = f"background: {color}"
            fmt.append(style)

        return fmt

    rating_color = get_rating_color(regr_result.rating, regr_result.improved)
    regr_df_html = pd.DataFrame([dict(
        improved=regr_result.improved,
        rating=regr_result.rating,
        rating_color=rating_color,
        description=regr_result.description,
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


def _generate_results_overview(all_regr_results_data, variables, kpis_common_prefix):
    entry_count = len(all_regr_results_data)
    first_column_name = variables[0] if variables else "name"

    all_regr_results_df = _generate_sorted_pd_table(all_regr_results_data, variables)
    def fmt(value):
        if is_nan(value):
            return ""

        return value.current_value_str

    kpi_names = set(all_regr_results_df.keys()[max([2, len(variables)+1]):])
    overview_fmt = {k: fmt for k in kpi_names}

    kpis_to_hide = []
    if not INCLUDE_ALL_THE_KPIS:
        for kpi_name in kpi_names:
            has_regression = False
            for kpi_value in all_regr_results_df[kpi_name].values:
                if kpi_value.rating != 0:
                    has_regression = True
                    break
            if not has_regression:
                kpis_to_hide.append(kpi_name)

    all_regr_results_df_html = all_regr_results_df\
        .style\
        .apply(get_all_regr_results_conditional_format(first_column_name, variables), axis = 1)\
        .format(overview_fmt)\
        .hide(axis="index")\
        .hide(kpis_to_hide, axis=1)\
        .set_table_styles(table_styles=STYLE_TABLE)

    return all_regr_results_df_html


def get_all_regr_results_conditional_format(first_column_name, variables):
    def all_regr_results_conditional_format(row):
        fmt = []

        for key, value in zip(row.keys(), row.values):

            if key in variables or key in ("name", "entry_id"):
                style = f"background: {COLOR_OVERVIEW_NAMES}; text-align: center;"
            else:
                # KPI result
                if is_nan(value):
                    style = "background: red"
                else:
                    color = get_rating_color(value.rating,  value.improved)
                    style = f"background: {color}; text-align: right;"

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


def _generate_details_table(regr_result):
    details_data = [regr_result.details] if isinstance(regr_result.details, dict) else regr_result.details
    regr_df_html = pd.DataFrame(details_data)\
                     .style\
                     .apply(regr_result.details_conditional_fmt, axis = 1)\
                     .format(regr_result.details_fmt)\
                     .hide(axis="index")\
                     .set_table_styles(table_styles=STYLE_TABLE)

    return regr_df_html

def _generate_comparison_plot(_comparison_df, comparison_keys, kpi_name, ref_kpi, kpis_common_prefix):
    data = []
    ref = None

    def create_name_column(row):
        return "|".join(f"{k}={row[k]}" for k in comparison_keys)

    comparison_df = _comparison_df.copy()
    comparison_df["name"] = comparison_df.apply(create_name_column, axis=1)

    fig = px.line(
        comparison_df, x="name", y="value",
        markers=True,
        title=f"{ref_kpi.help} (in {ref_kpi.unit})",
    )

    ref_name = comparison_df[comparison_df.ref == "*"].name.iloc[0]
    fig.add_hline(y=ref_kpi.value)
    fig.add_vline(x=ref_name)

    y_name = f"{kpi_name.replace(kpis_common_prefix, '')} (in {ref_kpi.unit})"
    if ref_kpi.lower_better is True:
        y_name = f"❮ {y_name}. Lower is better."
    elif ref_kpi.lower_better is False:
        y_name = f"{y_name}. Higher is better. ❯ "
    # ref_kpi.lower_better is None: nothing

    x_name = "|".join(comparison_keys)
    fig.update_yaxes(title=y_name, range=[0, comparison_df.value.max()*1.1])
    fig.update_xaxes(title=x_name)

    title = f"<b>{kpi_name}</b><br>{ref_kpi.help} (in {ref_kpi.unit})"

    fig.update_layout(title=title, title_x=0.5,)

    # not using dcc.Graph() here, so this will follow another path than plots in plotting reports.
    # here, fig.to_html() will be called.
    return html.Div([fig], style=dict(height="525px", width="100%"))
