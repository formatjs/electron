"""Source archive transport must retain exact refs and safe fallback URLs."""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//bcr/overlay/electron:archive_urls.bzl", "source_archive_urls")

def _impl(ctx):
    env = unittest.begin(ctx)
    for reference in ["abcdef012345", "refs/tags/v1.2.3", "refs/heads/branch"]:
        original = "https://github.com/owner/project/archive/" + reference + ".tar.gz"
        asserts.equals(env, ["https://codeload.github.com/owner/project/tar.gz/" + reference, original], source_archive_urls(original))
    for original in [
        "https://github.com/owner/project/releases/download/v1/source.tar.gz",
        "https://github.com/owner/project/archive/v1.zip",
        "https://github.com/owner/project/archive/.tar.gz",
        "https://github.com/owner/project/extra/archive/v1.tar.gz",
        "https://github.com.evil.invalid/owner/project/archive/v1.tar.gz",
        "https://example.invalid/owner/project/archive/v1.tar.gz",
    ]:
        asserts.equals(env, [original], source_archive_urls(original))
    return unittest.end(env)

archive_urls_test = unittest.make(_impl)
