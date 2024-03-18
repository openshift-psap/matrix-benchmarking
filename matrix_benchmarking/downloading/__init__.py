import logging
import enum

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

    raise ValueError(f"Download url '{url}' not supported :/")
