from bs4 import BeautifulSoup
import requests
import pathlib

import matrix_benchmarking.cli_args as cli_args

# lists
urls=[]

class ScrapOCPCiArtifactsBase():
    def __init__(self, workload_store, site, base_dir, result_local_dir):
        self.workload_store = workload_store
        self.site = site
        self.base_dir = base_dir
        self.result_local_dir = result_local_dir

    def download_file(self, filepath_rel, local_filename, depth):
        print(f"{' '*depth}File: {filepath_rel}")
        url = f"{self.site}/{self.base_dir}/{filepath_rel}"

        local_filename.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)


    def handle_file(self, filepath_rel, local_filename, depth):
        raise RuntimeError("not implemented ...")

    def scrape(self, current_href=None, depth=0):
        url = f"{self.site}{current_href if current_href else self.base_dir}"
        r = requests.get(url)
        s = BeautifulSoup(r.text,"html.parser")

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
                print(f"{' '*depth}Directory: {new_href.relative_to(self.base_dir)}")
                self.scrape(new_href, depth=depth+1)

            elif img_src == "/icons/file.png":
                # link to a file, delete to the child class to decide what to do with it
                rel_path = new_href.relative_to(self.base_dir)
                local_filename = self.result_local_dir / rel_path

                if local_filename.exists():
                    # file already downloaded, skip it
                    continue

                self.handle_file(rel_path, local_filename, depth)
            else:
                continue
