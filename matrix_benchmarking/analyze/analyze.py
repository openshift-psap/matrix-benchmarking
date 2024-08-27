from collections import defaultdict

from . import utils


IMPROVED_EVALUATION = {1: "in-line +", 2: "improved", 3:"improved +", 4: "improved++"}
DEGRADED_EVALUATION = {1: "in-line -", 2: "degraded", 3:"degraded +", 4: "degraded++"}


def do_regression_analyze(current_value, historical_values, lower_better):

    # Lets define schema for the dataFrame
    data = dict(
        current_value = current_value,
        previous_mean = utils.get_measure_of_mean(historical_values),
        std_dev = utils.get_measure_of_distribution(historical_values),
        change = utils.get_percentage_change(current_value, historical_values),
        delta = utils.get_delta(current_value, historical_values),
        historical_records_count = len(historical_values),
    )

    rating = 4
    improved = False
    for deviation in [1, 2, 3]:
        dev_dist, dev_bound, _improved = utils.get_std_dev_measurements(deviation, current_value, historical_values, lower_better)
        data[f"std_dev_{deviation}"] = dev_dist
        if rating != 4:
            data[f"std_dev_{deviation}_bound"] = None
            continue

        data[f"std_dev_{deviation}_bound"] = dev_bound
        if dev_bound:
            rating = deviation
        if _improved:
            improved = True

    data["rating"] = rating # lower is better

    data["evaluation"] = (IMPROVED_EVALUATION if improved else DEGRADED_EVALUATION)[rating]

    data["improved"] = improved

    return data
