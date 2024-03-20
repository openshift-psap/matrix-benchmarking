import requests
import pathlib
import logging
import urllib3
urllib3.disable_warnings()

from bs4 import BeautifulSoup

from matrix_benchmarking.downloading import DownloadModes
import matrix_benchmarking.cli_args as cli_args
from .. import BaseHttpScapper

class ScrapOCPCiArtifacts(BaseHttpScapper):

    def scrape(self, current_href=None, depth=0, test_found=False):
        url = f"{self.source_url.scheme}://{self.source_url.host}/{current_href if current_href else self.base_dir}"

        r = requests.get(url)
        s = BeautifulSoup(r.text,"html.parser")

        filenames = [(pathlib.Path(link.attrs['href']).name) for link in s.find_all("a")]
        cache_found = False

        if not test_found and ("exit_code" in filenames or "settings" in filenames):
            depth = 0
            test_found = True

        if test_found and depth == 0 and self.workload_store.CACHE_FILENAME in filenames:
            cache_found = True

        for link in s.find_all("a"):

            new_href = pathlib.Path(link.attrs['href'])

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

                if cache_found and self.download_only_cache:
                    logging.info(f"{' '*depth}Directory: {new_href.relative_to(self.base_dir)}: SKIP (cache found)")
                    continue

                logging.info(f"{' '*depth}Directory: {new_href.relative_to(self.base_dir)}")
                self.scrape(new_href, depth=depth+1, test_found=test_found)

            elif img_src == "/icons/file.png":
                # link to a file, defer to the child class to decide what to do with it
                rel_path = new_href.relative_to(self.base_dir)
                local_filename = self.result_local_dir / rel_path

                self.handle_file(rel_path, local_filename, depth)
            else:
                # ignore
                pass
