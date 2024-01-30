from matrix_benchmarking import regression

import numpy as np

class ZScoreIndicator(regression.RegressionIndicator):
    """
    Example regression indicator that uses the Z score as a metric
    to determine if the recent test was an outlier
    """
    def __init__(self, *args, threshold=3, **kwargs):
        super().__init__(*args, **kwargs)
        self.threshold = threshold

    def get_name(self):
        return f"ZScoreIndicator(threshold={self.threshold})"

    def regression_test(self, new_result: float, lts_results: np.array) -> regression.RegressionStatus:
        """
        Determine if the curr_result is more/less than threshold
        standard deviations away from the previous_results
        """
        mean = np.mean(lts_results)
        std = np.std(lts_results)
        z_score = (new_result - mean) / std

        status = 0
        explanation = "z-score not greater than threshold"
        details = {"threshold": self.threshold, "zscore": z_score}
        if abs(z_score) > self.threshold:
            status = 1
            direction = 1 if z_score > 0 else -1,
            explanation="z-score greater than threshold",

        return regression.RegressionStatus(0, direction=direction, explanation=explanation, details=details)
