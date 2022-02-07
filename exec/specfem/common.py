class objectview(object):
    def __init__(self, d):
        self.__dict__ = d

def set_artifacts_dir():
    global ARTIFACTS_DIR

    if sys.stdout.isatty():
        base_dir = Path("/tmp") / ("ci-artifacts_" + datetime.datetime.today().strftime("%Y%m%d"))
        base_dir.mkdir(exist_ok=True)
        current_length = len(list(base_dir.glob("*__*")))
        ARTIFACTS_DIR = base_dir / f"{current_length:03d}__benchmarking__run_specfem"
        ARTIFACTS_DIR.mkdir(exist_ok=True)
    else:
        ARTIFACTS_DIR = Path(os.getcwd())

    print(f"Saving artifacts files into {ARTIFACTS_DIR}")

    global ARTIFACTS_SRC
    ARTIFACTS_SRC = ARTIFACTS_DIR / "src"
    ARTIFACTS_SRC.mkdir(exist_ok=True)

def prepare_settings():
    settings = {}
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        settings[k] = v

    return settings
