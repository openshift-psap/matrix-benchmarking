from typing import Iterator

import os, types, itertools
from collections import defaultdict
import pathlib

import matrix_benchmarking

class LTSEntry(types.SimpleNamespace):
    def __init__(self, data: dict, metadata: dict, processed_key, import_key, processed_settings, import_settings):
        self.metadata = metadata
        self.data = data

        self.metrics: dict = data.get('metrics', {})
        self.thresholds: dict = data.get('thresholds', {})

        self.is_gathered = False
        self.is_lts = True
        
        Matrix.import_map[import_key] = self
        Matrix.processed_map[processed_key] = self
        
        [Matrix.settings[k].add(v) for k, v in processed_settings.items()]

    @staticmethod
    def from_dict(payload: dict, processed_key, import_key,  processed_settings, import_settings):
        try:
            return LTSEntry(payload['data'], payload['metadata'], processed_key, import_key, processed_settings, import_settings)
        except KeyError:
            return None
    
    def get_threshold(self, threshold_value, default: str = None) -> str:
        return self.thresholds.get(threshold_value, default)
    
    def get_name(self, variables) -> str:
        return ", ".join([f"{key}={self.metadata['settings'][key]}" for key in variables])
    
    def get_settings(self) -> dict:
        return self.metadata.get('settings', {})

    def check_thresholds(self) -> bool:
        return False #Not currently stored

class MatrixEntry(types.SimpleNamespace):
    def __init__(self, location, results,
                 processed_key, import_key,
                 processed_settings, import_settings, settings=None,
                 stats=None, is_gathered=None):
        if settings:
            self.settings = settings
        else:
            self.settings = types.SimpleNamespace()
        self.stats = {}

        self.location = location
        self.results = results

        self.settings.__dict__.update(processed_settings)
        self.processed_key = processed_key
        self.import_settings = processed_settings

        self.is_gathered = False
        self.is_lts = False

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
    def all_records(settings, setting_lists, include_local=True, include_lts=True) -> Iterator[MatrixEntry | LTSEntry]:
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
    def count_records(settings, setting_lists, include_local=True, include_lts=True):
        count = 0
        for settings_values in sorted(itertools.product(*setting_lists)):
            settings.update(dict(settings_values))
            key = Matrix.settings_to_key(settings)
            try:
                entry = Matrix.processed_map[key]
            except KeyError:
                continue # missing experiment
            if (entry.is_lts and include_lts) or (not entry.is_lts and include_local):
                count += 1
        return count

