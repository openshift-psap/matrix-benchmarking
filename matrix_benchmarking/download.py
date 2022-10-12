import os, sys
import logging
import urllib3
import pathlib

import matrix_benchmarking.store as store
import matrix_benchmarking.common as common
import matrix_benchmarking.cli_args as cli_args

import matrix_benchmarking.downloading.scrap as scrap

def main(url_file: str = "",
         workload: str = "",
         results_dirname: str = "",
         filters: list[str] = [],
         download: bool = False,
         ):
    """
Download MatrixBenchmarking results.

Env:
    MATBENCH_URL_FILE
    MATBENCH_WORKLOAD
    MATBENCH_RESULTS_DIRNAME
    MATBENCH_DOWNLOAD

See the `FLAGS` section for the descriptions.

Args:
    url_file: File where the URLs to download are stored.
    workload_dir: Name of the workload to execute. (Mandatory.)
    results_dirname: Name of the directory where the results will be stored. Can be set in the benchmark file. (Mandatory.)
    download: if 'False', list the locations that would be downloaded. If 'True', download them.
"""

    kwargs = dict(locals()) # capture the function arguments
    cli_args.setup_env_and_kwargs(kwargs)
    cli_args.check_mandatory_kwargs(kwargs, ("workload", "results_dirname",))

    def run():
        cli_args.store_kwargs(kwargs, execution_mode="download")

        workload_store = store.load_workload_store(kwargs)
        workload_store.load_interesting_files()

        with open(url_file) as f:
            urls = [line.strip() for line in f.readlines()]

        for dest_dirname__url in urls:
            dest_dirname, _, _url = dest_dirname__url.partition(" ")
            url = urllib3.util.url.parse_url(_url)
            site = f"{url.scheme}://{url.host}"
            base_dir = pathlib.Path(url.path)
            dest_dir = pathlib.Path(kwargs["results_dirname"]) / dest_dirname
            dest_dir.mkdir(parents=True, exist_ok=True)

            with open(dest_dir / "source_url", "w") as f:
                print(url, file=f)

            scrapper = ScrapOCPCiArtifacts(workload_store, site, base_dir, dest_dir)

            try:
                scrapper.scrape()
            except KeyboardInterrupt:
                print("Interrupted :/")
                break

        return 0

    return cli_args.TaskRunner(run)

class ScrapOCPCiArtifacts(scrap.ScrapOCPCiArtifactsBase):
    def handle_file(self, filepath_rel, local_filename, depth):
        if not self.workload_store.check_interesting_file(pathlib.Path("/not-used/"), filepath_rel, do_check=True):
            logging.debug(f"File: {filepath_rel}: SKIP")
            return # file isn't interesting, do not download it

        self.download_file(filepath_rel, local_filename, depth)
