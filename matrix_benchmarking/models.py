from typing import List, Tuple
import datetime as dt

from pydantic import BaseModel


class Metadata(BaseModel()):
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
