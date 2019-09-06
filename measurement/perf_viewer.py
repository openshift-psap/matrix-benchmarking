import json
import sys

import measurement
import measurement.perf_collect
import utils.live



class DummyLiveCollect(utils.live.LiveCollect):
    def connect(self, loop, process=None):
        self.alive = True
        pass

class Perf_Viewer(measurement.Measurement):
    quality_for_ui = None

    def __init__(self, cfg, experiment):
        measurement.Measurement.__init__(self, experiment)
        self.experiment = experiment
        self.live = DummyLiveCollect()
        if sys.stdin.isatty():
            raise IOError("Please launch the viewer with '... < file.db'")

    def setup(self):
        pass

    def start(self):
        input_f = sys.stdin

        quality = json.loads(input_f.readline())

        for entry in quality:
            self.experiment.new_quality(*entry)
        print(len(quality), "quality messages reloaded")

        if not Perf_Viewer.quality_for_ui:
            print("WARNING: quality graph markers not shared with UI.")

        while True:
            table_def = input_f.readline()
            if not table_def: break

            content_str = input_f.readline()
            quality_str = input_f.readline()

            _, table = measurement.perf_collect.create_table(self.experiment, table_def[:-1])
            for cpt, row in enumerate(json.loads(content_str)):
                table.add(*row)

            if Perf_Viewer.quality_for_ui:
                Perf_Viewer.quality_for_ui[table] = json.loads(quality_str)

            print(f"{table.table_name}: {cpt} rows reloaded.")
        print("Reloading completed.")

    def stop(self):
        pass

    def process_line(self, buf):
        pass
