import requests
import pathlib
import logging

from bs4 import BeautifulSoup

from matrix_benchmarking.downloading import DownloadModes
import matrix_benchmarking.cli_args as cli_args

# lists
urls=[]

class ScrapOCPCiArtifactsBase():
    def __init__(self, workload_store, site, base_dir, result_local_dir, do_download, download_mode):
        self.workload_store = workload_store
        self.site = site
        self.base_dir = base_dir
        self.result_local_dir = result_local_dir
        self.do_download = do_download
        self.download_mode = download_mode
        self.download_only_cache = self.download_mode in (DownloadModes.PREFER_CACHE, DownloadModes.CACHE_ONLY)
        self.cache_found = False

    def download_file(self, filepath_rel, local_filename, depth):
        logging.info(f"{' '*depth}File: {filepath_rel}: DOWNLOAD")

        url = f"{self.site}/{self.base_dir}/{filepath_rel}"

        if not self.do_download: return

        local_filename.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        page_not_found_anchor = str(self.base_dir.relative_to("/gcs") / filepath_rel)
        with open(local_filename) as f:
            try:
                for line in f.readlines():
                    if page_not_found_anchor not in line: continue
                    local_filename.unlink()

                    raise requests.exceptions.HTTPError(404, f"Page not found: {filepath_rel}")

            except UnicodeDecodeError:
                pass # file isn't unicode, it's can't be the 404 page

    def handle_file(self, filepath_rel, local_filename, depth):
        raise RuntimeError("not implemented ...")

    def scrape(self, current_href=None, depth=0):
        url = f"{self.site}{current_href if current_href else self.base_dir}"
        r = requests.get(url)
        s = BeautifulSoup(r.text,"html.parser")

        filenames = [(pathlib.Path(link.attrs['href']).name) for link in s.find_all("a")]
        if "exit_code" in filenames or "settings" in filenames:
            depth = 0

        if depth == 0:
            cache_file = pathlib.Path(self.workload_store.CACHE_FILENAME)
            try:
                self.handle_file(cache_file, self.result_local_dir / cache_file, depth)
                self.cache_found = True

            except requests.exceptions.HTTPError as e:
                if e.errno != 404: raise e

        for link in s.find_all("a"):

            new_href = pathlib.Path(link.attrs['href'])

            new_url = f"{self.site}{new_href}" # relative links not used in this platform

            if new_url in urls:
                # url already known, ignore
                continue

            img = link.find()
            if img is None and link.text == "gsutil":
                # link to download gsutil, ignore
                continue

            img_src = link.find("img")["src"]
            if img_src == "/icons/back.png":
                # link going to the parent directory, ignore
                continue

            if img_src == "/icons/dir.png":
                # link to a directory, recurse into it

                if self.cache_found and self.download_only_cache:
                    logging.info(f"{' '*depth}Directory: {new_href.relative_to(self.base_dir)}: SKIP (cache found)")
                    continue

                logging.info(f"{' '*depth}Directory: {new_href.relative_to(self.base_dir)}")
                self.scrape(new_href, depth=depth+1)

            elif img_src == "/icons/file.png":
                # link to a file, delete to the child class to decide what to do with it
                rel_path = new_href.relative_to(self.base_dir)
                local_filename = self.result_local_dir / rel_path

                self.handle_file(rel_path, local_filename, depth)
            else:
                continue
