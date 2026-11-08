"""Direct transport for pinned GitHub source archives."""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

def source_archive_urls(url):
    """Try codeload before GitHub's archive redirect; preserve all other URLs."""
    prefix = "https://github.com/"
    if not url.startswith(prefix) or not url.endswith(".tar.gz"):
        return [url]
    repository, separator, reference = url[len(prefix):].partition("/archive/")
    if not separator or len(repository.split("/")) != 2 or not all(repository.split("/")) or not reference[:-len(".tar.gz")]:
        return [url]
    return ["https://codeload.github.com/" + repository + "/tar.gz/" + reference[:-len(".tar.gz")], url]

def electron_source_archive(**kwargs):
    """Keep pinned http_archive inputs; make tar extraction type explicit."""
    urls = kwargs.get("urls", [])
    expanded = [candidate for url in urls for candidate in source_archive_urls(url)]
    if expanded != urls:
        if not kwargs.get("sha256") and not kwargs.get("integrity"):
            fail("Source archives require pinned integrity")
        kwargs["urls"] = expanded
        kwargs.setdefault("type", "tar.gz")
    http_archive(**kwargs)
