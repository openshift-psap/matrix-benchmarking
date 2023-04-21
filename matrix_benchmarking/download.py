import os, sys
import logging
import urllib3
import pathlib

import yaml

import matrix_benchmarking.store as store
import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args
from matrix_benchmarking.downloading import DownloadModes
import matrix_benchmarking.downloading.scrape as scrape

def main(url_file: str = "",
         url: str = "",
         workload: str = "",
         results_dirname: str = "",
         filters: list[str] = [],
         do_download: bool = False,
         mode: DownloadModes = None,
         ):
    """
Download MatrixBenchmarking results.

Download MatrixBenchmarking results.

Env:
    MATBENCH_URL_FILE
    MATBENCH_URL
    MATBENCH_WORKLOAD
    MATBENCH_RESULTS_DIRNAME
    MATBENCH_DO_DOWNLOAD
    MATBENCH_MODE

See the `FLAGS` section for the descriptions.

Args:
    url_file: File where the URLs to download are stored.
    url: URL that will be downloaded
    workload_dir: Name of the workload to execute. (Mandatory.)
    results_dirname: Name of the directory where the results will be stored. Can be set in the benchmark file. (Mandatory.)
    do_download: if 'False', list the files that would be downloaded. If 'True', download them.
    mode: 'prefer_cache' to download only the cache file, if it exists, or turn to 'mandatory' if it doesn't.
          'important' to download only the important files.
          'all' to download all the files.
"""

    kwargs = dict(locals()) # capture the function arguments
    cli_args.setup_env_and_kwargs(kwargs)
    cli_args.check_mandatory_kwargs(kwargs, ("workload", "results_dirname",))

    try:
        if not kwargs["mode"]:
            kwargs["mode"] = 'prefer_cache'

        kwargs["mode"] = DownloadModes(kwargs["mode"])
    except ValueError:
        logging.error(f"Invalid download mode: {kwargs['mode']}")
        return 1

    if not do_download:
        logging.warning("Running in DRY MODE (pass the flag --do-download to disable it)")

    def download_an_entry(an_entry, workload_store):
        destdir = an_entry["dest_dir"]
        destdir_url = urllib3.util.url.parse_url(an_entry["url"])
        settings = an_entry["settings"]

        site = f"{destdir_url.scheme}://{destdir_url.host}"
        base_dir = pathlib.Path(destdir_url.path)
        dest_dir = pathlib.Path(kwargs["results_dirname"]) / destdir

        if do_download:
            dest_dir.mkdir(parents=True, exist_ok=True)
            with open(dest_dir / "source_url", "w") as f:
                print(destdir_url, file=f)

            with open(dest_dir / "settings.from_url_file", "w") as f:
                for setting_key, setting_value in settings.items():
                    print(f"{setting_key}={setting_value}", file=f)

        def download(dl_mode):
            logging.info(f"Download {dest_dir} <-- {site}/{base_dir}")
            scrapper = ScrapOCPCiArtifacts(workload_store, site, base_dir, dest_dir, do_download, dl_mode)
            scrapper.scrape()

        def download_prefer_cache():
            if hasattr(workload_store, "load_cache"):
                download(DownloadModes.CACHE_ONLY)
                try:
                    if workload_store.load_cache(dest_dir):
                        return # download and reload from cache worked
                except FileNotFoundError:
                    pass

            # download or reload from cache worked failed, try again with the important files
            download(DownloadModes.IMPORTANT)

        if do_download and kwargs["mode"] == DownloadModes.PREFER_CACHE:
            download_prefer_cache()
        else:
            download(kwargs["mode"])

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="download")

        workload_store = store.load_workload_store(kwargs)

        if kwargs["url_file"]:
            try:
                with open(kwargs["url_file"]) as f:
                    data = yaml.safe_load(f)
            except FileNotFoundError as e:
                logging.error(f"Could not open the URL file: {e}")
                return 1

        elif kwargs["url"]:
            data = dict(download=[dict(url=kwargs["url"], dest_dir="expe/from_url", settings={})])

        else:
            logging.error("Please specify an URL file or an URL")
            return 1

        try:
            for entry in data["download"]:
                if "files" not in entry:
                    # download entry is here, download it
                    download_an_entry(entry, workload_store)
                    continue

                # download entries are in another file, process it
                for filename in entry["files"]:
                    with open(pathlib.Path(kwargs["url_file"]).parent / filename) as f:
                        download_file_data = yaml.safe_load(f)
                        for download_file_entry in download_file_data:
                            download_an_entry(download_file_entry, workload_store)

        except KeyboardInterrupt:
            print("Interrupted :/")
            return 1

        return 0

    return cli_args.TaskRunner(run)


class ScrapOCPCiArtifacts(scrape.ScrapOCPCiArtifactsBase):
    def handle_file(self, filepath_rel, local_filename, depth):
        if local_filename.exists():
            # file already downloaded, skip it
            return

        result_filepath_rel = pathlib.Path(*filepath_rel.parts[-(depth+1):])

        mandatory = self.workload_store.is_mandatory_file(result_filepath_rel)

        if (self.cache_found
            and self.download_only_cache
            and not mandatory):
            return # found the cache file, and not a mandatory file, continue.

        cache = self.workload_store.is_cache_file(result_filepath_rel)

        if self.download_mode == DownloadModes.CACHE_ONLY and not cache and not mandatory:
            logging.info(f"{' '*depth}File: {filepath_rel}: NOT CACHE/MANDATORY")
            return # file isn't important, do not download it

        important = True if cache or mandatory \
            else self.workload_store.is_important_file(result_filepath_rel)

        only_important_files = self.download_mode in (DownloadModes.IMPORTANT, DownloadModes.PREFER_CACHE)
        if only_important_files and not important:
            logging.info(f"{' '*depth}File: {filepath_rel}: NOT IMPORTANT")
            return # file isn't important, do not download it

        self.download_file(filepath_rel, local_filename, depth)
