from matrix_benchmarking import regression
from hunter import analysis
import numpy as np

def cp_to_details(cp):
    return {
        "index": int(cp.index),
        "mean_1": float(cp.stats.mean_1),
        "mean_2": float(cp.stats.mean_2),
        "std_1": float(cp.stats.std_1),
        "std_2": float(cp.stats.std_2),
        "pvalue": float(cp.stats.pvalue)
    }

class HunterWrapperIndicator(regression.RegressionIndicator):
    """
    Wrapper for datastax-labs/hunter
    """
    def __init__(self, *args, window_len: int = 50, max_pvalue: float = 0.001, min_magnitude: float = 0.05, **kwargs):
        super().__init__(*args, **kwargs)
        self.window_len = window_len
        self.max_pvalue = max_pvalue
        self.min_magnitude = min_magnitude

    def get_name(self):
        return f"HunterWrapperIndicator(window_len={self.window_len},max_pvalue={self.max_pvalue},min_magnitude={self.min_magnitude})"

    def regression_test(self, new_result: float, lts_results: np.array) -> regression.RegressionStatus:
        """
        Determine if the curr_result is more/less than threshold
        standard deviations away from the previous_results
        """

        series = np.concatenate((lts_results, [new_result]))

        change_points = analysis.compute_change_points(
            series,
            window_len=self.window_len,
            max_pvalue=self.max_pvalue,
            min_magnitude=self.min_magnitude
        )

        status = 0
        direction = 0
        explanation = "No change point detected with hunter"
        details = {
            "new_result": new_result,
            "change_points": [cp_to_details(p) for p in change_points]
        }

        if len(change_points) > 0:
            status = 1
            direction = 1 if change_points[-1].stats.forward_rel_change() > 0 else -1
            explanation="A change point was detected"

        return regression.RegressionStatus(status, direction=direction, explanation=explanation, details=details)
