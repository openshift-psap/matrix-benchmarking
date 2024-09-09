from collections import defaultdict
import statistics

from matrix_benchmarking.analyze import RegressionStatus

IMPROVED_DESCRIPTION = {0: "very close+", 1: "in-line +", 2: "improved", 3:"improved +", 4: "improved++"}
DEGRADED_DESCRIPTION = {0: "very close-", 1: "in-line -", 2: "degraded", 3:"degraded +", 4: "degraded++"}

COLOR_STDEV_BOUND = "#32CD32" # Lime Green
COLOR_STDEV_NOT_BOUND = "#FF5733" # Red brick
COLOR_STDEV_NONE = "lightgreen"

########

MAX_STDEV = 4

########

def do_regression_analyze(current_value, historical_values, lower_better, kpi_unit):
    details = dict(
        current_value = current_value,
        previous_mean = get_measure_of_mean(historical_values),
        std_dev = get_measure_of_distribution(historical_values),
        change = get_percentage_change(current_value, historical_values),
        delta = get_delta(current_value, historical_values),
    )

    below = current_value < details["previous_mean"]

    improved = (below and lower_better) or (not below and not lower_better) \
        if lower_better is not None else None

    found_in_stdev = MAX_STDEV
    for deviation in range(1, MAX_STDEV):
        dev_dist, dev_bound = get_std_dev_measurements(deviation, current_value, historical_values)
        details[f"std_dev_{deviation}"] = dev_dist
        if found_in_stdev != MAX_STDEV:
            details[f"std_dev_{deviation}_bound"] = None
            continue

        details[f"std_dev_{deviation}_bound"] = dev_bound
        if dev_bound:
            found_in_stdev = deviation

    description = (IMPROVED_DESCRIPTION if improved else DEGRADED_DESCRIPTION)[found_in_stdev]
    rating = found_in_stdev / MAX_STDEV
    accepted = (improved or found_in_stdev < MAX_STDEV)

    return RegressionStatus(
        rating = rating,
        accepted = accepted,
        details = details,
        details_fmt = __get_details_fmt(kpi_unit),
        details_conditional_fmt = __get_details_conditional_fmt,
        improved = improved,
        description = description,
    )

######
######
######

def __get_details_fmt(kpi_unit):
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


def __get_details_conditional_fmt(row):
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


#######################
#######################
#######################

# Calculate sample/population mean

def get_measure_of_mean(data):
    '''
    Returns Mean to determine the limits
    '''
    if len(data) == 1:
        return data[-1]

    if len(data) == 0:
        return 0

    return statistics.mean(data)


# Calculate sample/population standard deviation

def get_measure_of_distribution(data):
    '''
    Returns STDDEV to determine the limits
    '''
    if len(data) == 1:
        return data[-1]

    if len(data) == 0:
        return 0


    return statistics.stdev(data)


def get_std_dev_measurements(deviation, current_mean, previous_data):
    '''
    Returns standard deviation bounds
    '''

    previous_data_mean = get_measure_of_mean(previous_data)
    previous_data_stddev = get_measure_of_distribution(previous_data)

    if deviation == 1:
        std_lower_bound = previous_data_mean - (previous_data_stddev * deviation)
        std_upper_bound = previous_data_mean + (previous_data_stddev * deviation)

        number_of_observation = len([item for item in previous_data if item <= std_upper_bound and item >= std_lower_bound])
        if current_mean <= std_upper_bound and current_mean >= std_lower_bound:
            bound_verify = True
        else:
            bound_verify = False

    else:
        std_lower_bound_1 = previous_data_mean - (previous_data_stddev * (deviation - 1))
        std_upper_bound_1 = previous_data_mean + (previous_data_stddev * (deviation - 1))

        std_lower_bound_2 = previous_data_mean - (previous_data_stddev * deviation)
        std_upper_bound_2 = previous_data_mean + (previous_data_stddev * deviation)

        number_of_observation_below_the_mean = len([item for item in previous_data if item <= std_lower_bound_1 and item >= std_lower_bound_2])
        number_of_observation_above_the_mean = len([item for item in previous_data if item >= std_upper_bound_1 and item <= std_upper_bound_2])

        number_of_observation = number_of_observation_above_the_mean + number_of_observation_below_the_mean

        if current_mean <= std_lower_bound_1 and current_mean >= std_lower_bound_2:
            bound_verify = True
        elif current_mean >= std_upper_bound_1 and current_mean <= std_upper_bound_2:
            bound_verify = True
        else:
            bound_verify = False

    pct = 0 if len(previous_data) <= 1 \
        else (number_of_observation / len(previous_data)) * 100

    return pct, bound_verify


def get_percentage_change(mean, previous_data):
    '''
    Returns %change w.r.t the average mean
    '''

    previous_data_mean = get_measure_of_mean(previous_data)
    if previous_data_mean == 0:
        return 100
    else:
        return (((mean / previous_data_mean) * 100) - 100)


def get_delta(mean, previous_data):
    '''
    Returns the difference of current_mean and previous_mean
    '''

    previous_data_mean = get_measure_of_mean(previous_data)
    return (mean - previous_data_mean)
