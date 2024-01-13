from typing import Iterator

import os, types, itertools
from collections import defaultdict
import pathlib

import matrix_benchmarking


class MatrixEntry(types.SimpleNamespace):
    def __init__(self, location, results,
                 processed_key, import_key,
                 processed_settings, import_settings, settings=None,
                 stats=None, is_gathered=None):
        self.is_gathered = False

        self.settings = settings or types.SimpleNamespace()

        self.stats = {}

        self.location = location
        self.results = results

        self.settings.__dict__.update(processed_settings)

        self.processed_key = processed_key
        self.import_settings = processed_settings

        Matrix.import_map[import_key] = \
        Matrix.processed_map[processed_key] = self

        [Matrix.settings[k].add(v) for k, v in processed_settings.items()]

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



class Matrix():
    settings = defaultdict(set)
    import_map = {}
    processed_map = {}

    @staticmethod
    def settings_to_key(settings):
        return "|".join(f"{k}={settings[k]}" for k in sorted(settings) if k != "stats")

    @staticmethod
    def all_records(settings, setting_lists) -> Iterator[MatrixEntry]:
        for settings_values in sorted(itertools.product(*setting_lists)):
            settings.update(dict(settings_values))
            key = Matrix.settings_to_key(settings)

            try:
                yield Matrix.processed_map[key]
            except KeyError: # missing experiment, ignore
                continue

    @staticmethod
    def get_record(settings):
        key = Matrix.settings_to_key(settings)

        return Matrix.processed_map.get(key, None)

    @staticmethod
    def count_records(settings, setting_lists):
        return sum([ 1 for _ in Matrix.all_records(settings, setting_lists)]) # don't use len(list(...)) with a generator, this form is more memory efficient

    @staticmethod
    def has_records(settings, setting_lists):
        try:
            _first_entry = next(Matrix.all_records(settings, setting_lists)) # raises an exception is the generator is empty
            return True
        except StopIteration:
            return False
