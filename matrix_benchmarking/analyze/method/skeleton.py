from matrix_benchmarking.analyze import RegressionStatus

###

def do_regression_analyze(current_value, historical_values, lower_better, kpi_unit):
    # anything useful to understand the analyze in the report
    details = dict(
        current_value = current_value,
        historical_values = historical_values,
        lower_better = lower_better,
        kpi_unit = kpi_unit,
    )

    # indicator telling if the current value is better or worst than the historical values
    improved = current_value < min(historical_values) if lower_better \
        else current_value > max(historical_values)

    # indicator telling if the current value should be accepted or rejected (rejects will turn the CI red)
    accepted = improved

    # a rating indicating the regression level of the current value against the historical values
    # 0 is in-line, no deviation is measured
    # <1 deviation is accepted
    # >=1 deviation is too important
    # 'improved' tells the direction of the deviation (better result or worst)
    rating = 0.2

    # human readable text describing the rating
    description = "good" if improved else "bad"

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
    def historical_values_fmt(value):
        return "["+", ".join([f"{v:.2f}" for v in value])+"] " + kpi_unit

    return dict(
        current_value="{:.2f} "+kpi_unit,
        historical_values=historical_values_fmt,
    )


def __get_details_conditional_fmt(row):
    fmt = []
    for key, value in zip(row.keys(), row.values):
        style = "background: palegreen"

        fmt.append(style)

    return fmt
