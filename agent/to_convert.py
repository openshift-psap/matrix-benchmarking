import measurement.perf_viewer
import experiment
import os, sys

def convert(rec_db_path):
    if not rec_db_path.endswith(".rec"):
        raise NameError("Recorded log DB filename should end with '.rec'")

    db_name = rec_db_path[:-4]
    db_path = db_name + ".db"

    if os.path.exists(db_path) and sys.stdin.isatty():
        print(f"File '{db_path}' already exists. Add a new experimentation to to the DB? [Y/n] ", end="")
        if input().startswith("n"):
            print("Aborting.")
            exit(1)

    expe = experiment.Experiment({}, db_name=db_name)

    viewer = measurement.perf_viewer.Perf_Viewer(None, expe,
                                                 open(rec_db_path))
    viewer.setup()
    viewer.start()
    viewer.stop()

    expe.save()
    print(f"Recorded log DB saved into '{db_path}'.")
    print("---")
    return db_path
