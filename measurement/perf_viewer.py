import json
import sys

import measurement
import measurement.perf_collect
import utils.live

viewer_mode = False

class DummyLiveCollect(utils.live.LiveCollect):
    def connect(self, loop, process=None):
        self.alive = True
        pass

class Perf_Viewer(measurement.Measurement):
    quality_for_ui = None

    def __init__(self, cfg, experiment, input_f=None):
        measurement.Measurement.__init__(self, experiment)
        self.experiment = experiment
        self.live = DummyLiveCollect()

        if input_f is None:
            try:
                self.input_f = open(sys.argv[2])
            except (IndexError, FileNotFoundError):
                raise IOError("Please launch the viewer with "+" ".join(sys.argv+["FILE.rec"]))
        else:
            self.input_f = input_f

        global viewer_mode
        viewer_mode = True

    def setup(self):
        pass

    def start(self):
        quality = json.loads(self.input_f.readline())

        for entry in quality:
            self.experiment.new_quality(*entry)
        print(len(quality), "quality messages reloaded")

        if Perf_Viewer.quality_for_ui is None:
            print("WARNING: quality graph markers not shared with UI.")

        while True:
            _table_def = self.input_f.readline()
            if not _table_def: break

            content_str = self.input_f.readline()
            quality_str = self.input_f.readline()

            mode = _table_def.split()[1].split(".")[0]
            table_def = _table_def.replace(f" {mode}.", " ")[:-1]

            _, table = measurement.perf_collect.create_table(self.experiment, table_def, mode)
            for cpt, row in enumerate(json.loads(content_str)):
                table.add(*row)

            if Perf_Viewer.quality_for_ui is not None:
                Perf_Viewer.quality_for_ui[table] = json.loads(quality_str)

            print(f"{table.table_name}: {cpt} rows reloaded.")
        print("Reloading completed.")
        self.input_f.close()

    def stop(self):
        pass

    def process_line(self, buf):
        pass
