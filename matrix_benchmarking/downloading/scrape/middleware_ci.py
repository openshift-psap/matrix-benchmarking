import requests
import pathlib
import logging

from bs4 import BeautifulSoup

from matrix_benchmarking.downloading import DownloadModes
import matrix_benchmarking.cli_args as cli_args

import urllib3
urllib3.disable_warnings()

# lists
urls=[]

class ScrapMiddlewareCiArtifacts():
    def __init__(self, workload_store, site, base_dir, result_local_dir, do_download, download_mode):
        self.workload_store = workload_store
        self.site = site
        self.base_dir = base_dir
        self.result_local_dir = result_local_dir
        self.do_download = do_download
        self.download_mode = download_mode
        self.download_only_cache = self.download_mode in (DownloadModes.PREFER_CACHE, DownloadModes.CACHE_ONLY)

    def download_file(self, filepath_rel, local_filename, depth):
        logging.info(f"{' '*depth}File: {filepath_rel}: DOWNLOAD")

        url = f"{self.site}/{self.base_dir}/{filepath_rel}"

        if not self.do_download: return

        local_filename.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(url, stream=True, verify=False) as r:
            try:
                r.raise_for_status()
            except:
                import pdb;pdb.set_trace()
                pass
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

    def scrape(self, current_href=None, depth=0, found=False):
        url = f"{self.site}{current_href if current_href else self.base_dir}"

        r = requests.get(url, verify=False)
        s = BeautifulSoup(r.text,"html.parser")

        links = [svg.parent.next_sibling.find("a") for svg in s.find_all("svg", {"class": "icon-sm"})]
        filenames = [link.text for link in links]
        cache_found = False

        if not found and ("exit_code" in filenames or "settings" in filenames):
            depth = 0
            found = True
            logging.info(f"Found a base directory at {url}")

        if found and depth == 0:
            cache_file = current_href / self.workload_store.CACHE_FILENAME
            try:
                rel_path = cache_file.relative_to(self.base_dir)
                local_filename = self.result_local_dir / rel_path

                self.handle_file(rel_path, local_filename, depth)

                logging.info(f"Cache found :) {cache_file}")
                cache_found = True
            except requests.exceptions.HTTPError as e:
                if e.errno != 404: raise e
                logging.info(f"Cache not found :( {cache_file}")

        for link in links:
            new_href = (current_href or self.base_dir) / pathlib.Path(link.attrs['href'])

            new_url = f"{self.site}{new_href}" # relative links not used in this platform

            if new_url in urls:
                # url already known, ignore
                continue

            svg_class = link.parent.previous_sibling.find("svg").attrs["class"] # always exists, because of the way links/link is located

            if "icon-folder" in svg_class:
                # link to a directory, recurse into it

                if cache_found and self.download_only_cache:
                    logging.info(f"{' '*depth}Directory: {new_href.relative_to(self.base_dir)}: SKIP (cache found)")
                    continue

                logging.info(f"{' '*depth}Directory: {new_href.relative_to(self.base_dir)}")
                self.scrape(new_href, depth=depth+1, found=found)

            elif found and "icon-document" in svg_class:
                # link to a file, defer to the child class to decide what to do with it
                rel_path = new_href.relative_to(self.base_dir)
                local_filename = self.result_local_dir / rel_path

                self.handle_file(rel_path, local_filename, depth)
            else:
                continue

    def handle_file(self, filepath_rel, local_filename, depth):
        if local_filename.exists():
            # file already downloaded, skip it
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

        self.download_file(filepath_rel, local_filename, depth)
