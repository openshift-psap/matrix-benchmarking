from __future__ import annotations

from typing import List, Tuple, Dict, Union, Optional
import datetime as dt
import enum
import inspect
import datetime

from pydantic import BaseModel, ConstrainedStr, constr, Extra, Field, UUID4
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


class PSAPEnum(str, enum.Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.replace('_', ' ')

    def __str__(self) -> str:
        return self.value


class EntryStatus(PSAPEnum):
    Valid = enum.auto()
    Invalid = enum.auto()


class Empty(ExclusiveModel):
    ...


class Metadata(ExclusiveModel):
    status: EntryStatus = Field(default=EntryStatus.Valid)

    start: dt.datetime
    end: dt.datetime
    settings: Dict[str, Union[str, int]]
    test_uuid: UUID4
    urls: Optional[List[str]]


class PrometheusValue(ExclusiveModel):
    metric: Dict[str, str]
    values: Dict[int, float]

PrometheusValues = List[PrometheusValue]

PrometheusNamedMetricValues = Dict[str, PrometheusValues]

class PrometheusMetric(ExclusiveModel):
    query: str
    data: PrometheusValues


class SemVer(ConstrainedStr):
    regex = f"^{SEMVER_REGEX}$"


def create_schema_field(schema_name):
    return constr(regex = f"^urn:{schema_name}:{SEMVER_REGEX}$")


class KPI(ExclusiveModel):
    unit: str
    help: str
    timestamp: datetime.datetime = Field(..., alias="@timestamp")
    value: Union[float, int, List[float], List[int]]
    test_uuid: UUID4

    status: EntryStatus = Field(default=EntryStatus.Valid)

    ci_engine: Optional[str]
    run_id: Optional[str]
    test_path: Optional[str]

    urls: Optional[dict[str, str]]

    def __str__(self):
        labels = {k:v for k, v in self.__dict__.items() if k not in ("unit", "help", "timestamp", "value")}
        labels_str = ", ".join(f"{k}=\"{v}\"" for k, v in labels.items())

        return f"""# HELP {self.help}, in {self.unit}
__NAME__{{{labels_str}}} {self.value} {self.unit}"""

def KPIMetadata(**kwargs):
    def decorator(fct):
        mod = inspect.getmodule(fct)

        name = fct.__name__
        if name in mod.KPIs:
            raise KeyError(f"Key {name} already exists in module {fct.__module__}.")

        mod.KPIs[name] = kwargs.copy()
        mod.KPIs[name]["__func__"] = fct

        return fct

    return decorator


def getKPIsModel(name, module_name, KPIs, KPImodel):
    model = pydantic.create_model(
        name,
        __base__=ExclusiveModel,
        **dict(zip(KPIs.keys(), [(KPImodel, ...) for _ in range(len(KPIs))])),
        __module__=module_name
    )

    def tostr(self):
        return "\n".join([str(getattr(self, name)).replace("__NAME__", name) for name in self.__fields__.keys()])

    model.tostr = tostr

    return model

class RegressionResult(ExclusiveModel):
    kpi: str
    setting: str
    indicator: str
    status: int
    direction: Optional[int] = Field(default=None)
    explanation: Optional[str] = Field(default=None)
    details: Optional[dict[str, str]] = Field(default=None)
