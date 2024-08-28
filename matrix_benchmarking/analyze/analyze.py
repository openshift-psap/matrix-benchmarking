from collections import defaultdict
import types
from typing import Optional, Callable
import math

from . import utils

IMPROVED_EVALUATION = {1: "in-line +", 2: "improved", 3:"improved +", 4: "improved++"}
DEGRADED_EVALUATION = {1: "in-line -", 2: "degraded", 3:"degraded +", 4: "degraded++"}

COLOR_STDEV_BOUND = "#32CD32" # Lime Green
COLOR_STDEV_NOT_BOUND = "#FF5733" # Red brick
COLOR_STDEV_NONE = "lightgreen"

RATING_MAX = 4

def is_nan(entry):
    return isinstance(entry, float) and math.isnan(entry)


class RegressionStatus(types.SimpleNamespace):
    def __init__(
            self,
            accepted: bool,
            rating: int,
            rating_max: int,
            rating_color: Optional[str] = None,
            improved: Optional[int] = None,
            evaluation: Optional[str] = None,
            details: Optional[dict] = None,
            details_fmt: Optional[dict] = None,
            details_conditional_fmt: Optional[Callable] = None,
        ):
        self.rating = rating
        self.rating_color = rating_color
        self.rating_max = rating_max
        self.improved = improved
        self.evaluation = evaluation

        self.details = details
        self.details_fmt = details_fmt
        self.details_conditional_fmt = details_conditional_fmt


def get_details_fmt(kpi_unit):
    return dict(
        current_value="{:.2f} "+kpi_unit,
        previous_mean="{:.2f} "+kpi_unit,
        std_dev="{:.1f}",
        std_dev_1="{:.1f} %",
        std_dev_2="{:.1f} %",
        std_dev_3="{:.1f} %",
        change="{:.1f} %",
        delta="{:.1f}"
    )


def get_details_conditional_fmt(row):
    fmt = []
    for key, value in zip(row.keys(), row.values):
        style = ""

        if key in ["std_dev_1_bound", "std_dev_2_bound", "std_dev_3_bound"]:
            if value is True:
                style = f"background: {COLOR_STDEV_BOUND}"  # green
            elif value is False:
                style = f"background: {COLOR_STDEV_NOT_BOUND}"  # red
            elif value is None:
                style = f"background: {COLOR_STDEV_NONE}"

        fmt.append(style)

    return fmt

def do_regression_analyze(current_value, historical_values, lower_better, kpi_unit):
    # Lets define schema for the dataFrame
    details = dict(
        current_value = current_value,
        previous_mean = utils.get_measure_of_mean(historical_values),
        std_dev = utils.get_measure_of_distribution(historical_values),
        change = utils.get_percentage_change(current_value, historical_values),
        delta = utils.get_delta(current_value, historical_values),
    )

    below = current_value < details["previous_mean"]

    improved = (below and lower_better) or (not below and not lower_better) \
        if lower_better is not None else None

    rating = RATING_MAX
    for deviation in [1, 2, 3]:
        dev_dist, dev_bound = utils.get_std_dev_measurements(deviation, current_value, historical_values)
        details[f"std_dev_{deviation}"] = dev_dist
        if rating != 4:
            details[f"std_dev_{deviation}_bound"] = None
            continue

        details[f"std_dev_{deviation}_bound"] = dev_bound
        if dev_bound:
            rating = deviation

    return RegressionStatus(
        rating = rating,
        rating_max = RATING_MAX,
        accepted = (not improved and rating == 4),
        details = details,
        details_fmt = get_details_fmt(kpi_unit),
        details_conditional_fmt = get_details_conditional_fmt,
        improved = improved,
        evaluation = (IMPROVED_EVALUATION if improved else DEGRADED_EVALUATION)[rating],
    )
