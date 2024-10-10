from collections import defaultdict
import types
from typing import Optional, Callable
import math

class RegressionStatus(types.SimpleNamespace):
    def __init__(
            self,
            accepted: bool,
            rating: int,
            rating_color: Optional[str] = None,
            improved: Optional[int] = None,
            description: Optional[str] = None,
            details: Optional[dict] = None,
            details_fmt: Optional[dict] = None,
            details_conditional_fmt: Optional[Callable] = None,
        ):
        self.rating = rating
        self.rating_color = rating_color
        self.improved = improved
        self.description = description
        self.accepted = accepted

        self.details = details
        self.details_fmt = details_fmt
        self.details_conditional_fmt = details_conditional_fmt

def do_regression_analyze(*args, **kwargs):
    # lazy loading of hunter package ...
    from .method import hunter as analyze_method

    return analyze_method.do_regression_analyze(*args, **kwargs)
