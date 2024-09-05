from matrix_benchmarking.analyze import RegressionStatus

import numpy as np

THRESHOLD = 3

def do_regression_analyze(current_value, historical_values, lower_better, kpi_unit):
    """
    Determine if the curr_result is more/less than threshold
    standard deviations away from the previous_results
    """

    historical_mean = np.mean(historical_values)
    if len(historical_values) == 1:
        std = 0
        z_score = 0
    else:
        std = np.std(historical_values)
        z_score = (current_value - historical_mean) / std

    details = {
        "current_value": current_value,
        "historical_mean": historical_mean,
        "threshold": THRESHOLD,
        "zscore": z_score,
        "stddev": std
    }
    improved = True if z_score > 0 else False
    if len(historical_values) == 1:
        accepted = None
        description = "Not enough historical values"
    elif abs(z_score) < THRESHOLD:
        accepted = True
        description = "z-score lower than threshold"
    else:
        accepted = False
        description = "z-score greater than threshold"

    rating = abs(z_score / THRESHOLD)

    if accepted is None:
        rating = None

    return RegressionStatus(
        rating = rating,
        accepted = accepted,
        details = details,
        improved = improved,
        description = description,
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
