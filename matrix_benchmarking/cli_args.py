import yaml
import json
import os, sys
import pathlib
import logging
import importlib
import json

kwargs = None
experiment_filters = {}
cli_environ = {}

def store_kwargs(_kwargs, *, execution_mode):
    global kwargs
    kwargs = _kwargs
    kwargs["execution_mode"] = execution_mode


def get_benchmark_yaml_file(benchmark_file):
    if not benchmark_file:
        benchmark_file = os.environ.get("MATBENCH_BENCHMARK_FILE")

    if not benchmark_file:
        raise ValueError("benchmark_file must be passed in the command-line or with the MATBENCH_BENCHMARK_FILE environment variable.")

    benchmark_file_path = pathlib.Path(os.path.realpath(benchmark_file))

    if not benchmark_file_path.exists():
        raise FileNotFoundError(f"'{benchmark_file}' does not exit.")
    if not benchmark_file_path.is_file():
        raise FileNotFoundError(f"'{benchmark_file}' must be a file.")

    # parse the benchmark file YAML
    logging.info(f"Loading the benchmark file {benchmark_file} ...")
    with open(benchmark_file_path) as f:
        benchmark_yaml_file = yaml.safe_load(f)

    return benchmark_yaml_file


def update_env_with_env_files():
    """
    Overrides the function default args with the flags found in the environment variables files
    """

    for env in ".env", ".env.generated", ".env.yaml",".env.json", ".env.generated.json", ".env.generated.yaml":
        env_file = pathlib.Path(env)
        if not env_file.exists(): continue
        with open(env) as f:
            if env_file.suffix in (".yaml", ".json"):
                doc = yaml.safe_load(f) if env_file.suffix == ".yaml" else json.load(f)
                for k, v in doc.items():
                    key = f"MATBENCH_{k.upper()}"
                    cli_environ[key] = str(v)
            else:
                for line in f.readlines():
                    key, found , value = line.strip().partition("=")
                    if not found:
                        logging.warning("invalid line in {env}: {line.strip()}")
                        continue
                    if key in os.environ and os.environ[key]: continue # prefer env to env file
                    cli_environ[key] = value


def update_kwargs_with_env(kwargs):
    # override the function default args with the flags found in the environment variables

    for flag, current_value in kwargs.items():
        if current_value: continue # already set, ignore.
        key = f"MATBENCH_{flag.upper()}"
        env_value = os.environ.get(key)
        if not env_value:
            # not set as environment var
            env_value = cli_environ.get(key)
            if not env_value: continue # not set in an environment file, ignore

        kwargs[flag] = env_value # override the function arg with the environment variable value


def update_kwargs_with_benchmark_file(kwargs, benchmark_desc_file):
    # override the function default args with the flags found in the benchmark file
    for flag, current_value in kwargs.items():
        if current_value: continue # already set, ignore.

        for item_name in (f"--{flag.replace('_', '-')}", f"--{flag}"):
            file_value = benchmark_desc_file.get(item_name)
            if file_value is None: continue # not set, ignore.
            kwargs[flag] = file_value # override the function arg with the benchmark file value

            del benchmark_desc_file[item_name]
            break

    # warn for every flag remaining in the benchmark file
    for key, value in benchmark_desc_file.items():
        if not key.startswith("--"): continue

        logging.warning(f"unexpected flag found in the benchmark file: {key} = '{value}'")


def check_mandatory_kwargs(kwargs, mandatory_flags, sensitive_flags = []):
    command = [f"matbench {sys.argv[1]}"]
    for k, v in sorted(kwargs.items()):
        if v not in mandatory_flags and not v: continue

        value = "<OMITTED>" if k in sensitive_flags else v
        command += [f"--{k.replace('_', '-')}='{value}'"]

    logging.info("MatrixBenchmarking starting with:\n" + " \\\n\t".join(command))

    err = False
    for flag in mandatory_flags:
        if kwargs.get(flag): continue

        logging.fatal(f"--{flag} must be set in CLI, in the benchmark file or though MATBENCH_{flag.upper()} environment variable.")
        err = True

    if err:
        raise SystemExit(1)


def setup_env_and_kwargs(kwargs):
    # overriding order: env file <- env var <- benchmark file <- cli
    update_env_with_env_files()
    update_kwargs_with_env(kwargs)

    kwargs["max_records"] = 10000 if "max_records" not in kwargs else kwargs.get("max_records")
    filters = kwargs.get("filters")
    if isinstance(filters, bool):
        filters = str(filters)

def parse_filters(filters):
    for kv in filters.split(","):
        key, found, value = kv.partition("=")
        if not found:
            logging.error(f"Unexpected filter value: {kv}")
            sys.exit(1)

        value = value.replace("\\:", "<escaped colon>")
        value = value.split(":") if ":" in value else [value]
        value = [v.replace("<escaped colon>", ":") for v in value]

        experiment_filters[key] = value

class TaskRunner:
    """
    TaskRunner

    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    If you're seeing this text, put the --help flag earlier in your list
    of command-line arguments, this is a limitation of the CLI parsing library
    used by the MatrixBenchmarking.
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    """
    def __init__(self, run):
        self.run = run

    def __str__(self): return "---"
