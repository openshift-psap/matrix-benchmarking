from typing import Iterator
import logging
import os, types, itertools
from collections import defaultdict
import pathlib

import matrix_benchmarking


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
        
        self.import_key = import_key
        self.processed_key = processed_key
        self.import_settings = processed_settings

        matrix.import_map[import_key] = \
        matrix.processed_map[processed_key] = self

        [matrix.settings[k].add(v) for k, v in processed_settings.items()]

    def get_name(self, variables) -> str:
        return ", ".join([f"{key}={self.settings.__dict__[key]}" for key in variables])

    def get_threshold(self, threshold_value, default: str = None) -> str:
        if hasattr(self.results, 'thresholds'):
            return self.results.thresholds.get(threshold_value, default)
        return default

    def get_settings(self) -> dict:
        return self.settings.__dict__

    def check_thresholds(self) -> bool:
        return hasattr(self.results, 'check_thresholds') and self.results.check_thresholds


class MatrixDefinition():
    def __init__(self, is_lts=False):
        self.settings = defaultdict(set)
        self.import_map = {}
        self.processed_map = {}
        self.is_lts = is_lts

    def settings_to_key(self, settings):
        return "|".join(f"{k}={settings[k]}" for k in sorted(settings) if k != "stats")

    def all_records(self, settings=None, setting_lists=None) -> Iterator[MatrixEntry]:
        if settings is None and setting_lists is None:
            yield from self.processed_map.values()
            return

        for settings_values in sorted(itertools.product(*setting_lists)):
            settings.update(dict(settings_values))
            key = self.settings_to_key(settings)

            try:
                yield self.processed_map[key]
            except KeyError: # missing experiment, ignore
                continue

    def get_record(self, settings):
        key = self.settings_to_key(settings)

        return self.processed_map.get(key, None)

    def count_records(self, settings=None, setting_lists=None):
        if settings is None and setting_lists is None:
            return len(self.processed_map)

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
            self.settings[key] = sorted(values)

            value_str = ", ".join(map(str, self.settings[key]))
            if self.is_lts and key == "@timestamp":
                value_str = f"<{len(self.settings)}x values>"

            logging.info(f"{key:20s}: {value_str}")

        logging.info("---")

        return True


Matrix = MatrixDefinition()
LTS_Matrix = MatrixDefinition(is_lts=True)
