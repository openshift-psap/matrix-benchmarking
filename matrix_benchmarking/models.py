from __future__ import annotations

from typing import List, Tuple, Dict, Union, Optional
import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConstrainedStr, constr, Extra
import pydantic

SEMVER_REGEX="(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"

class ExclusiveModel(BaseModel):
    __force_annotation: int # workaround for https://github.com/python/cpython/issues/95532, for AllOptional 'annotations.update(base.__annotations__)' to work

    class Config:
        extra = Extra.forbid

class AllOptional(pydantic.main.ModelMetaclass):
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


class PSAPEnum(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.replace('_', ' ')


class SemVer(ConstrainedStr):
    regex = f"^{SEMVER_REGEX}$"
