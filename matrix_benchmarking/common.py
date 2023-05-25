from typing import Iterator

import os, types, itertools
from collections import defaultdict
import pathlib

import matrix_benchmarking


class MatrixEntry(types.SimpleNamespace):
    def __init__(self, location, results,
                 processed_key, import_key,
                 processed_settings, import_settings, settings=None,
                 stats=None, is_gathered=None, is_lts=False):
        self.is_lts = is_lts
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
    def all_records(settings, setting_lists, include_local=True, include_lts=False, local_first=True) -> Iterator[MatrixEntry]:
        if local_first: # Does nothing if both are not set to true, this is to provide a default behaviour
            if include_local and include_lts:
                yield from Matrix.all_records(settings, setting_lists, include_local=True, include_lts=False)
                yield from Matrix.all_records(settings, setting_lists, include_local=False, include_lts=True)
                return

        for settings_values in sorted(itertools.product(*setting_lists)):
            settings.update(dict(settings_values))
            key = Matrix.settings_to_key(settings)

            try:
                entry = Matrix.processed_map[key]
            except KeyError:
                continue # missing experiment
            if (entry.is_lts and include_lts) or (not entry.is_lts and include_local):
                yield entry

    @staticmethod
    def get_record(settings):
        key = Matrix.settings_to_key(settings)

        try: return Matrix.processed_map[key]
        except KeyError: return None

    @staticmethod
    def count_records(settings, setting_lists, include_local=True, include_lts=False):
        return sum([ 1 for _ in Matrix.all_records(settings, setting_lists, include_local, include_lts) ])

    @staticmethod
    def has_records(settings, setting_lists, include_local=True, include_lts=False):
         for _ in Matrix.all_records(settings, setting_lists, include_local, include_lts):
              return True
         return False
