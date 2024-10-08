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
    exit_code: Optional[int]


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
    lower_better: Optional[bool]

    status: EntryStatus = Field(default=EntryStatus.Valid)

    ci_engine: Optional[str]
    run_id: Optional[str]
    test_path: Optional[str]

    urls: Optional[dict[str, str]]

    #
    ignored_for_regression: Optional[bool] = Field(exclude=True)
    format: Optional[str] = Field(exclude=True)
    full_format: Optional[str] = Field(exclude=True)
    divisor: Optional[float] = Field(exclude=True)
    divisor_unit: Optional[str] = Field(exclude=True)
    #

    def __str__(self):
        labels = {k:v for k, v in self.__dict__.items() if k not in ("unit", "help", "timestamp", "value")}
        labels_str = ", ".join(f"{k}=\"{v}\"" for k, v in labels.items())

        return f"""# HELP {self.help}, in {self.unit}
__NAME__{{{labels_str}}} {self.value} {self.unit}"""


def IgnoredForRegression(fct):
    mod = inspect.getmodule(fct)

    name = fct.__name__

    if name not in mod.KPIs:
        raise KeyError(f"@IgnoredForRegression should come before @KPIMetadata() for {name}")

    mod.KPIs[name]["ignored_for_regression"] = True

    return fct


def LowerBetter(fct):
    mod = inspect.getmodule(fct)

    name = fct.__name__

    if name not in mod.KPIs:
        raise KeyError(f"@LowerBetter should come before @KPIMetadata() for {name}")

    if mod.KPIs[name].get("lower_better") is not None:
        raise KeyError(f"@LowerBetter should not be used with @HigherBetter for {name}")

    mod.KPIs[name]["lower_better"] = True

    return fct


def HigherBetter(fct):
    mod = inspect.getmodule(fct)

    name = fct.__name__

    if name not in mod.KPIs:
        raise KeyError(f"@HigherBetter should come before @KPIMetadata() for {name}")

    if mod.KPIs[name].get("lower_better") is not None:
        raise KeyError(f"@HigherBetter should not be used with @LowerBetter for {name}")

    mod.KPIs[name]["lower_better"] = False

    return fct

#
# Receives a divisor to apply to the value before formatting it
# 100, "MB"
#
def FormatDivisor(divisor: float, unit: str, format:str = None):
    def decorator(fct):
        mod = inspect.getmodule(fct)

        name = fct.__name__

        if name not in mod.KPIs:
            raise KeyError(f"@FormatDivisor should come before @KPIMetadata() for {name}")

        if format:
            if mod.KPIs[name].get("format") is not None:
                raise KeyError(f"@FormatDivisor(fmt) should not be used with @Format for {name}")
            mod.KPIs[name]["format"] = format
        else:
            if mod.KPIs[name].get("format") is None:
                raise KeyError(f"@FormatDivisor should be used with @Format for {name}")

        mod.KPIs[name]["divisor"] = divisor
        mod.KPIs[name]["divisor_unit"] = unit

        return fct

    return decorator

#
# Receives a format string as parameter
# eg: "{.2f}"
#
def Format(format: str):
    def decorator(fct):
        mod = inspect.getmodule(fct)

        name = fct.__name__

        if name not in mod.KPIs:
            raise KeyError(f"@Format should come before @KPIMetadata() for {name}")

        if mod.KPIs[name].get("full_format"):
            raise KeyError(f"@Format should not be used with @FullFormat for {name}")

        mod.KPIs[name]["format"] = format

        return fct

    return decorator

#
# Receives a KPI as parameter
# eg:
def FullFormat(format_fct):
    def decorator(fct):
        mod = inspect.getmodule(fct)

        name = fct.__name__
        if callable(format_fct) and mylambda.__name__ == "<lambda>":
            raise KeyError(f"@FullFormat does not work with Lambda for {name}")

        if name not in mod.KPIs:
            raise KeyError(f"@FullFormat should come before @KPIMetadata() for {name}")

        if mod.KPIs[name].get("format"):
            raise KeyError(f"@FullFormat should not be used with @Format for {name}")

        mod.KPIs[name]["full_format"] = format_fct

        return fct

    return decorator


def KPIMetadata(help, unit):

    def decorator(fct):
        mod = inspect.getmodule(fct)

        name = fct.__name__
        if name in mod.KPIs:
            raise KeyError(f"Key {name} already exists in module {fct.__module__}.")

        mod.KPIs[name] = dict(help=help, unit=unit)
        mod.KPIs[name]["__func__"] = fct
        mod.KPIs[name]["ignored_for_regression"] = False
        mod.KPIs[name]["format"] = None
        mod.KPIs[name]["full_format"] = None
        mod.KPIs[name]["divisor"] = None
        mod.KPIs[name]["divisor_unit"] = None
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
