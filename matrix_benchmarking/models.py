from typing import List, Tuple, Dict, Union
import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConstrainedStr, constr, Extra

SEMVER_REGEX="(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"

class ExclusiveModel(BaseModel):
    class Config:
        extra = Extra.forbid

class Metadata(ExclusiveModel):
    start: dt.datetime
    end: dt.datetime


def create_PSAPPayload(schema_name):
    class PSAPPayload(ExclusiveModel):
        """
        The underlying model of PSAP payloads
        """
        payload_schema: constr(regex=f"^urn:{schema_name}:{SEMVER_REGEX}$")
        data: dict
        metadata: Metadata

        class Config:
            fields = {'payload_schema': '$schema'}
    return PSAPPayload

class Empty(BaseModel):
    ...

    class Config:
        extra = "forbid"

class PrometheusValue(ExclusiveModel):
    metric: Dict[str, str]
    values: List[Tuple[int, str]]

PrometheusValues = Union[List[PrometheusValue], Empty]

class PrometheusMetric(ExclusiveModel):
    query: str
    data: PrometheusValues


class PSAPEnum(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.replace('_', ' ')


class SemVer(ConstrainedStr):
    regex = f"^{SEMVER_REGEX}$"
