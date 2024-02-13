import os
import json
import logging
import types
import datetime
import numpy as np
from functools import reduce
from typing import Optional, Callable
import copy

import matrix_benchmarking.common as common
import matrix_benchmarking.models as models

def get_from_path(d, path):
    return reduce(dict.get, path.split("."), d)

# check if ALL (k, v) pairs in part are present in full_dict
def dict_part_eq(part, full_dict):
    return reduce(lambda x, y: x and part[y] == full_dict[y], part.keys(), True)

class RegressionStatus(types.SimpleNamespace):
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
            new_payload: common.MatrixEntry,
            lts_payloads: list[common.MatrixEntry],
            x_var: str,
            x_var_key = lambda x: x.metadata.end.astimezone(),
            kpis: Optional[list[str]] = None,
            settings_filter: Optional[dict] = None,
            combine_funcs: dict = {},
            use_x_var = False # Automatically determine the settings for the x_var
        ):
        self.new_payload = new_payload
        self.x_var = x_var
        self.x_var_key = x_var_key
        self.kpis = kpis
        self.combine_funcs = combine_funcs
        self.settings_filter = settings_filter
        self.use_x_var = use_x_var

        if self.settings_filter and self.x_var:
            logging.warning("settings_filter and x_var set, only using settings_filter")
        elif self.x_var and self.use_x_var:
            settings = dict(self.new_payload.get_settings())
            settings.pop(self.x_var)
            self.settings_filter = settings

        if self.settings_filter:
            # Only store payloads that have equivalent (k, v) pairs
            # as the settings_filter
            self.lts_payloads = list(
                filter(
                    lambda x: dict_part_eq(self.settings_filter, x.get_settings()),
                    lts_payloads
                )
            )

            if not dict_part_eq(self.settings_filter, self.new_payload.get_settings()):
                self.new_payload = None
                logging.warning("settings_filter isn't satisfied for the new payload")
        else:
            self.lts_payloads = lts_payloads


    def get_name(self):
        return "UndefinedRegressionIndicator"

    def analyze(self) -> list[models.Regression]:

        if not self.new_payload or not self.lts_payloads:
            logging.info("Missing a new payload or lts payloads")
            return [
                models.Regression(
                    kpi="",
                    metric="" if not self.x_var else self.x_var,
                    indicator=self.get_name(),
                    status=0
                )
            ]

        regression_results = []

        kpis_to_test = vars(self.new_payload.results.lts.kpis).keys() if not self.kpis else self.kpis
        for kpi in kpis_to_test:

            curr_values = []
            if type(self.new_payload.results) is list:
                for result in self.new_payload.results:
                    curr_values.append(vars(result.lts.kpis)[kpi].value)
            else:
                curr_values.append(vars(self.new_payload.results.lts.kpis)[kpi].value)

            lts_values = []
            for payload in self.lts_payloads:
                if type(payload.results) is list:
                    lts_values += list(map(lambda x: vars(x.results.kpis)[kpi].value, payload.results))
                else:
                    lts_values.append(vars(payload.results.kpis)[kpi].value)


            if any(map(lambda x: type(x) is list, curr_values + lts_values)):
                if kpi in self.combine_funcs:
                    curr_values = [self.combine_funcs[kpi](v) for v in curr_values]
                    lts_values = [self.combine_funcs[kpi](v) for v in lts_values]
                else:
                    logging.warning(f"Skipping KPI with list of values, consider filtering KPIs or providing a combine_func for {kpi}")
                    continue

            for curr_value in curr_values:
                raw_results: RegressionStatus = self.regression_test(curr_value, lts_values)
                result = models.Regression(
                    kpi=kpi,
                    metric="" if not self.x_var else self.x_var,
                    indicator=self.get_name(),
                    status=raw_results.status,
                    direction=raw_results.direction,
                    explanation=raw_results.explanation,
                    details=raw_results.details
                )
                regression_results.append(result)

        return regression_results

    def regression_test(self, new_result: float, lts_result: np.array) -> RegressionStatus:
        return RegressionStatus(0, explanation="Default return status")
