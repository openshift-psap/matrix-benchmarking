import logging
import enum
import pathlib
import requests


class DownloadModes(enum.Enum):
    CACHE_ONLY = "cache_only"
    PREFER_CACHE = "prefer_cache"
    IMPORTANT = "important"
    ALL = "all"


def get_scrapper_class(url):
    # lazy loading to avoid circular imports

    if "openshiftapps.com" in url.host:
        logging.info("OpenShift CI scrapping detected.")

        import matrix_benchmarking.downloading.scrape.ocp_ci as ocp_ci_scrapper
        return ocp_ci_scrapper.ScrapOCPCiArtifacts

    if "ci.app-svc-perf.corp.redhat.com" in url.host:
        logging.info("Middleware CI scrapping detected.")

        import matrix_benchmarking.downloading.scrape.middleware_ci as middleware_ci_scrapper
        return middleware_ci_scrapper.ScrapMiddlewareCiArtifacts

    if url.scheme == "s3":
        logging.info("S3 scrapping detected.")

        import matrix_benchmarking.downloading.scrape.s3 as s3_scrapper
        return s3_scrapper.ScrapS3

    raise ValueError(f"Download url '{url}' not supported :/")


class BaseScapper():

    def __init__(self, workload_store, source_url, base_dir, result_local_dir, do_download, download_mode):
        self.workload_store = workload_store
        self.source_url = source_url
        self.base_dir = base_dir
        self.result_local_dir = result_local_dir
        self.do_download = do_download
        self.download_mode = download_mode
        self.download_only_cache = self.download_mode in (DownloadModes.PREFER_CACHE, DownloadModes.CACHE_ONLY)

    def download_file(self, filepath_rel, local_filename, depth, handler):
        raise NotImplemented()

    def scrape(self, current_href=None, depth=0, test_found=False):
        raise NotImplemented()

    def handle_file(self, filepath_rel, local_filename, depth, handler=None):
        if local_filename.exists():
            # file already downloaded, skip it
            logging.info(f"{' '*depth}File: {filepath_rel}: EXISTS")
            return

        result_filepath_rel = pathlib.Path(*filepath_rel.parts[-(depth+1):])

        mandatory = self.workload_store.is_mandatory_file(result_filepath_rel)

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

        logging.info(f"{' '*depth}File: {filepath_rel}: DOWNLOAD")
        self.download_file(filepath_rel, local_filename, depth, handler)


class BaseHttpScapper(BaseScapper):
    def download_file(self, filepath_rel, local_filename, depth, handler):
        url = f"{self.source_url.scheme}://{self.source_url.host}/{self.base_dir}/{filepath_rel}"

        if not self.do_download: return

        local_filename.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(url, stream=True, verify=False) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
