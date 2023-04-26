import os, types, itertools
from collections import defaultdict
import pathlib

import matrix_benchmarking

class LTSEntry(types.SimpleNamespace):
    def __init__(self, data: dict, metadata: dict, processed_key, import_key, processed_settings, import_settings):
        self.metadata = metadata
        self.data = data

        self.is_gathered = False
        
        Matrix.import_map[import_key] = self
        Matrix.processed_map[processed_key] = self
        
        [Matrix.settings[k].add(v) for k, v in processed_settings.items()]

    @staticmethod
    def from_dict(payload: dict, processed_key, import_key,  processed_settings, import_settings):
        try:
            return LTSEntry(payload['data'], payload['metadata'], processed_key, import_key, processed_settings, import_settings)
        except KeyError:
            return None


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

        Matrix.import_map[import_key] = \
        Matrix.processed_map[processed_key] = self

        [Matrix.settings[k].add(v) for k, v in processed_settings.items()]


class Matrix():
    settings = defaultdict(set)
    import_map = {}
    processed_map = {}

    @staticmethod
    def settings_to_key(settings):
        return "|".join(f"{k}={settings[k]}" for k in sorted(settings) if k != "stats")

    @staticmethod
    def all_records(settings, setting_lists):
        for settings_values in sorted(itertools.product(*setting_lists)):
            settings.update(dict(settings_values))
            key = Matrix.settings_to_key(settings)
            try:
                yield Matrix.processed_map[key]
            except KeyError:
                continue # missing experiment

    @staticmethod
    def get_record(settings):
        key = Matrix.settings_to_key(settings)

        try: return Matrix.processed_map[key]
        except KeyError: return None

