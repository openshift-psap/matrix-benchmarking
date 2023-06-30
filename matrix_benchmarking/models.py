from __future__ import annotations

from typing import List, Tuple, Dict, Union, Optional
import datetime as dt
from enum import Enum

from pydantic.v1 import BaseModel, ConstrainedStr, constr, Extra
import pydantic

SEMVER_REGEX="(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"

class ExclusiveModel(BaseModel):
    __force_annotation: int # workaround for https://github.com/python/cpython/issues/95532, for AllOptional 'annotations.update(base.__annotations__)' to work

    class Config:
        extra = Extra.forbid

class AllOptional(pydantic.v1.main.ModelMetaclass):
    def __new__(self, name, bases, namespaces, **kwargs):
        annotations = namespaces.get('__annotations__', {})
        for base in bases:
            annotations.update(base.__annotations__)
        for field in annotations:
            if not field.startswith('__'):
                annotations[field] = Optional[annotations[field]]
        namespaces['__annotations__'] = annotations
        return super().__new__(self, name, bases, namespaces, **kwargs)

class Metadata(ExclusiveModel):
    start: dt.datetime
    end: dt.datetime
    settings: Dict[str, Union[str, int]]


class Empty(ExclusiveModel):
    ...


class PrometheusValue(ExclusiveModel):
    metric: Dict[str, str]
    values: List[Tuple[int, str]]

PrometheusValues = Union[List[PrometheusValue], Empty]

PrometheusNamedMetricValues = Dict[str, PrometheusValues]

class PrometheusMetric(ExclusiveModel):
    query: str
    data: PrometheusValues


class PSAPEnum(str, Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.replace('_', ' ')

    def __str__(self) -> str:
        return self.value

class SemVer(ConstrainedStr):
    regex = f"^{SEMVER_REGEX}$"

def create_schema_field(schema_name):
    return constr(regex = f"^urn:{schema_name}:{SEMVER_REGEX}$")
