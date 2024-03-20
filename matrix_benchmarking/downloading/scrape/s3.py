import requests
import pathlib
import logging
import boto3

from matrix_benchmarking.downloading import DownloadModes
import matrix_benchmarking.cli_args as cli_args
from .. import BaseScapper

class ScrapS3(BaseScapper):

    def download_file(self, filepath_rel, local_filename, depth, handler):
        logging.info(f"{' '*depth}File: {filepath_rel}: DOWNLOAD")

        if not self.do_download: return

        s3_client = handler

        local_filename.parent.mkdir(parents=True, exist_ok=True)

        s3_client.download_file(self.source_url.host, str(self.base_dir / filepath_rel).strip("/"), local_filename)

        if not local_filename.exists():
            raise RuntimeError(f"Something unexpected happened, {local_filename} does not exist :/")

    def scrape(self, current_href=None, depth=0, test_found=False, handler=None):
        if handler is None:
            session = boto3.Session() # use the env/default settings to login into AWS
            handler = boto3.client("s3")

        s3_client = handler

        current_dir = current_href or self.base_dir
        response = s3_client.list_objects_v2(Bucket=self.source_url.host, Prefix=str(current_dir).strip("/") + "/", Delimiter="/")


        filenames = [pathlib.Path(entry["Key"]).name for entry in response.get("Contents", [])]
        dirnames = [pathlib.Path(entry["Prefix"]).name for entry in response.get("CommonPrefixes", [])]

        cache_found = False

        if not test_found and self.is_test_directory(filenames):
            depth = 0
            test_found = True
            logging.info(f"Found a test directory at {current_dir}")

        if self.has_cache_file(filenames, test_found, depth):
            cache_found = True

        for filename in filenames:
            new_href = (current_href or self.base_dir) / filename
            rel_path = new_href.relative_to(self.base_dir)
            local_filename = self.result_local_dir / rel_path

            self.handle_file(rel_path, local_filename, depth, handler)

        for dirname in dirnames:
            new_href = (current_href or self.base_dir) / dirname

            if cache_found and self.download_only_cache:
                logging.info(f"{' '*depth}Directory: {new_href.relative_to(self.base_dir)}: SKIP (cache found)")
                continue

            logging.info(f"{' '*depth}Directory: {new_href.relative_to(self.base_dir)}")
            self.scrape(new_href, depth=depth+1, test_found=test_found)
