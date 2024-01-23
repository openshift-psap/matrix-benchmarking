import os
import json

import numpy as np
from functools import reduce
from typing import Optional, Callable

import matrix_benchmarking.common as common

def get_from_path(d, path):
    return reduce(dict.get, path.split("."), d)

# check if ALL (k, v) pairs in part are present in full_dict
def dict_part_eq(part, full_dict):
    return reduce(lambda x, y: x and part[y] == full_dict[y], part.keys(), True)

class RegressionStatus:
    def __init__(
            self,
            status: int,
            direction: Optional[int] = None,
            explanation: Optional[str] = None,
            details: Optional[dict] = None
        ):
        self.status = status
        self.direction = direction
        self.explanation = explanation
        self.details = details


class RegressionIndicator:
    """
    Assume the matrix that is passed in contains a prefiltered combination of settings,
    or pass in the desired filter with the setings_filter option
    """
    def __init__(
            self,
            new_payloads: list[common.MatrixEntry],
            lts_payloads: list[common.MatrixEntry],
            x_var_key = lambda x: x.results.metadata.end,
            kpis: Optional[list[str]] = None,
            settings_filter: Optional[dict] = None,
        ):
        self.x_var_key = x_var_key
        self.kpis = kpis
        self.settings_filter = settings_filter

        if self.settings_filter:
            # Only store payloads that have equivalent (k, v) pairs
            # as the settings_filter
            self.new_payloads = list(
                filter(
                    lambda x: dict_part_eq(self.settings_filter, x),
                    map(lambda x: x.settings, new_payloads)
                )
            )
            self.lts_payloads = list(
                filter(
                    lambda x: dict_part_eq(self.settings_filter, x),
                    map(lambda x: x.settings, lts_payloads)
                )
            )
        else:
            self.new_payloads = new_payloads
            self.lts_payloads = lts_payloads

        # Why isn't this working? I suspect gnarly python stuff
        # self.lts_payloads.sort(key=lambda entry: self.x_var_key(entry))


    def analyze(self) -> list[dict]:

        if not self.new_payloads:
            return [(None, "", RegressionStatus(0, explanation="Not enough new data"))]
        elif not self.lts_payloads:
            return [(None, "", RegressionStatus(0, explanation="Not enough LTS data"))]

        regression_results = []
        for curr_result in self.new_payloads:
            print(curr_result)
            kpis_to_test = vars(curr_result.results.lts.kpis).keys() if not self.kpis else self.kpis
            for kpi in kpis_to_test:
                regression_results.append(
                    {
                        "result": curr_result,
                        "kpi": kpi,
                        "regression": self.regression_test(
                            vars(curr_result.results.lts.kpis)[kpi].value,
                            list(map(lambda x: vars(x.results.kpis).value, self.lts_payloads))
                        )
                    }
                )
                print(regression_results)
        return regression_results

    def regression_test(self, new_result: float, lts_result: np.array) -> RegressionStatus:
        return RegressionStatus(0, explanation="Default return status")


class ZScoreIndicator(RegressionIndicator):
    """
    Example regression indicator that uses the Z score as a metric
    to determine if the recent test was an outlier
    """
    def __init__(self, *args, threshold=3, **kwargs):
        super().__init__(*args, **kwargs)
        self.threshold = threshold

    def regression_test(self, new_result, lts_results) -> RegressionStatus:
        """
        Determine if the curr_result is more/less than threshold
        standard deviations away from the previous_results
        """
        mean = np.mean(prev_results)
        std = np.std(prev_results)
        z_score = (curr_result - mean) / std
        if abs(z_score) > self.threshold:
            return RegressionStatus(
                1,
                direction=1 if z_score > 0 else -1,
                explanation="z-score greater than threshold",
                details={"threshold": self.threshold, "zscore": z_score}
            )
        else:
            return RegressionStatus(
                0,
                explanation="z-score not greater than threshold",
                details={"threshold": self.threshold, "zscore": z_score}
            )

class PolynomialRegressionIndicator(RegressionIndicator):
    """
    Placeholder for polynomial regression that we could implement
    somewhere in the pipeline
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def regression_test(self, curr_result, prev_results) -> RegressionStatus:
        return RegressionStatus(0, explanation="Not implemented")

class HunterWrapperIndicator(RegressionIndicator):
    """
    Some straightfoward indicators are implemented above but this also provides what should
    be a simple way to wrap datastax/Hunter in a regression_test
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def regression_test(self, curr_result, prev_results) -> RegressionStatus:
        return RegressionStatus(0, explanation="Not implemented")
