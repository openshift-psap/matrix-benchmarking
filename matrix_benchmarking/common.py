from typing import Iterator
import logging
import os, types, itertools
from collections import defaultdict
import pathlib

import matrix_benchmarking

MISSING_SETTING_VALUE = None

class MatrixEntry(types.SimpleNamespace):
    def __init__(self, location, results,
                 processed_key, import_key,
                 processed_settings, import_settings,
                 matrix,
                 settings=None,
                 stats=None, is_gathered=None):
        self.is_gathered = False

        self.settings = settings or types.SimpleNamespace()

        self.stats = {}

        self.location = location
        self.results = results

        self.settings.__dict__.update(processed_settings)

        self.processed_key = processed_key
        self.import_settings = processed_settings

        matrix.import_map[import_key] = \
        matrix.processed_map[processed_key] = self

        keys_to_skip = set()
        for k, v in processed_settings.items():
            if not k.__hash__:
                #logging.warn(f"Key {k} not unhashable (type {k.__class__}). Skipping it.")
                keys_to_skip.add(k)
                continue
            elif not v.__hash__:
                #logging.warn(f"Value {k}={v} not unhashable (type {k.__class__}). Skipping this key.")
                keys_to_skip.add(k)

        [matrix.settings[k].add(v) for k, v in processed_settings.items() if k not in keys_to_skip]

    def get_name(self, variables) -> str:
        return ", ".join([f"{key}={self.settings.__dict__[key]}" for key in variables
                          if self.settings.__dict__[key] is not MISSING_SETTING_VALUE
                          and len([v for v in Matrix.settings[key] if v is not MISSING_SETTING_VALUE]) > 1])

    def get_threshold(self, threshold_value, default: str = None) -> str:
        if hasattr(self.results, 'thresholds'):
            return self.results.thresholds.get(threshold_value, default)
        return default

    def get_settings(self) -> dict:
        return self.settings.__dict__

    def check_thresholds(self) -> bool:
        return hasattr(self.results, 'check_thresholds') and self.results.check_thresholds


class MatrixKey(dict):
    def __init__(self, settings):
        self.settings = settings

    def __str__(self):
        return "|".join(f"{k}={self.settings[k]}" for k in sorted(self.settings) if k != "stats")

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash(str(self))

LTS_META_KEYS = [
    "kpi_settings_version",
    "lts_schema_version",
    "help", "unit", "@timestamp", "value",
    "run_id", "urls",
    "test_uuid",
]

class MatrixDefinition():
    def __init__(self, is_lts=False):
        self.settings = defaultdict(set)
        self.import_map = {}
        self.processed_map = {}
        self.is_lts = is_lts

    def settings_to_key(self, settings):
        return MatrixKey(settings)

    def all_records(self, settings=None, setting_lists=None, gathered=False) -> Iterator[MatrixEntry]:

        if settings is None and setting_lists is None:
            for e in self.processed_map.values():
                if (gathered and e.is_gathered) or (not gathered and not e.is_gathered):
                    yield e
            return

        for settings_values in sorted(itertools.product(*setting_lists), key=lambda x:x[0][0] if x else None):
            settings.update(dict(settings_values))

            key = self.settings_to_key(settings)
            try:
                e = self.processed_map[key]
            except KeyError: # missing experiment, ignore
                continue

            if (gathered and e.is_gathered) or (not gathered and not e.is_gathered):
                yield e

    def get_record(self, settings):
        key = self.settings_to_key(settings)

        return self.processed_map.get(key, None)

    def count_records(self, settings=None, setting_lists=None):
        if settings is None and setting_lists is None:
            return sum(1 for e in self.processed_map.values() if not e.is_gathered)

        return sum([ 1 for _ in self.all_records(settings, setting_lists)]) # don't use len(list(...)) with a generator, this form is more memory efficient

    def has_records(self, settings, setting_lists):
        try:
            _first_entry = next(self.all_records(settings, setting_lists)) # raises an exception is the generator is empty
            return True
        except StopIteration:
            return False

    def print_settings_to_log(self):
        if not self.processed_map:
            return False

        logging.info("Settings matrix:")

        for key, values in self.settings.items():
            if key == "stats": continue

            self.settings[key] = sorted(values, key=lambda x: (x is MISSING_SETTING_VALUE, x))

            value_str = ", ".join(map(str, self.settings[key]))
            if self.is_lts and key == "@timestamp":
                value_str = f"<{len(self.settings)}x values>"

            logging.info(f"{key:20s}: {value_str}")

        logging.info("---")

        return True

    def uniformize_settings_keys(self):
        orig_processed_map = dict(self.processed_map)

        self.processed_map = {}
        for entry_key, entry in orig_processed_map.items():
            for settings_key in self.settings.keys():
                if settings_key in entry_key.settings: continue

                entry_key.settings[settings_key] = MISSING_SETTING_VALUE
                self.settings[settings_key].add(MISSING_SETTING_VALUE)
                entry.settings.__dict__[settings_key] = MISSING_SETTING_VALUE

            self.processed_map[entry_key] = entry

Matrix = MatrixDefinition()
LTS_Matrix = MatrixDefinition(is_lts=True)
