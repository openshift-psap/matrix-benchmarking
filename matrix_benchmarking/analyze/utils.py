from collections import defaultdict
import statistics


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


def get_std_dev_measurements(deviation, current_mean, previous_data, lower_better):
    '''
    Returns standard deviation bounds
    '''

    previous_data_mean = get_measure_of_mean(previous_data)
    previous_data_stddev = get_measure_of_distribution(previous_data)

    below = current_mean <= previous_data_mean
    improved = below and lower_better

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

    return pct, bound_verify, improved


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
