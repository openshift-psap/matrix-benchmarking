from hunter import analysis
import numpy as np

from matrix_benchmarking.analyze import RegressionStatus

###

WINDOW_LEN = 50
MAX_PVALUE = 0.001
MIN_MAGNITUDE = 0.05

###

def do_regression_analyze(current_value, historical_values, lower_better, kpi_unit):

    values = historical_values + [current_value]

    change_points = analysis.compute_change_points(
        values,
        window_len=WINDOW_LEN,
        max_pvalue=MAX_PVALUE,
        min_magnitude=MIN_MAGNITUDE
    )

    status = 0
    direction = 0
    explanation = "No change point detected with hunter"
    details = [cp_to_details(p) for p in change_points]

    if len(change_points):
        direction = change_points[-1].stats.forward_rel_change()
        # direction > 0 --> value increased
        # direction < 0 --> value decreated
        decreased = direction < 0
        increased = not decreased
        improved = (decreased and lower_better) or (increased and not lower_better)

        # if the current value is alone in its statistical group:
        if change_points[-1].index == len(historical_values):
            accepted = False
            evaluation = "Jump" if improved else "Regression"
            rating = 1
        else:
            accepted = True
            evaluation = f"Inline ({len(change_points)} historical)"
            rating = 0

    else:
        accepted = True
        evaluation = "Inline"
        rating = 0
        improved = None

    return RegressionStatus(
        rating = rating,
        accepted = accepted,
        details = details,
        improved = improved,
        evaluation = evaluation,
        # a function to format the content of the details cells
        details_fmt = __get_details_fmt(kpi_unit),
        # a function to style the details cells
        details_conditional_fmt = __get_details_conditional_fmt,
    )


###

def __get_details_fmt(kpi_unit):
    return dict()


def __get_details_conditional_fmt(row):
    fmt = []
    for key, value in zip(row.keys(), row.values):
        style = "background: palegreen"

        fmt.append(style)

    return fmt

###

def cp_to_details(cp):
    return {
        "index": int(cp.index),
        "mean_1": float(cp.stats.mean_1),
        "mean_2": float(cp.stats.mean_2),
        "std_1": float(cp.stats.std_1),
        "std_2": float(cp.stats.std_2),
        "pvalue": float(cp.stats.pvalue),
        "forward_rel_change": cp.stats.forward_rel_change(),
    }
