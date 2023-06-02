from typing import List, Tuple
import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConstrainedStr


class Metadata(BaseModel):
    start: dt.datetime
    end: dt.datetime


class PSAPPayload(BaseModel):
    """
    The underlying model of PSAP payloads
    """
    data: dict
    metadata: Metadata


class PrometheusValue(BaseModel):
    metric: dict
    values: List[Tuple[int, str]]


class PrometheusMetric(BaseModel):
    query: str
    data: List[PrometheusValue]


class PSAPEnum(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.replace('_', ' ')


class SemVer(ConstrainedStr):
    regex = "^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"

