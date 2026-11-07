"""Pin ICU independently of other source repository implementations."""

def _impl(ctx):
    revision = "1b2e3e8a421efae36141a7b932b41e315b089af8"
    dependency = ctx.read(ctx.attr.chromium).partition("'src/third_party/icu':")[2].partition("\n\n")[0]
    if "'/chromium/deps/icu.git' + '@' + '" + revision + "'" not in dependency:
        fail("Pinned ICU revision differs from Electron's Chromium DEPS")
    integrity = "sha256-Y7ha2oVUxB/rO1rnLCk9koACgW/V8VDaoFEju7G/u28="
    ctx.download_and_extract(
        url = "https://github.com/foolip/chromium-icu/archive/" + revision + ".tar.gz",
        integrity = integrity,
        stripPrefix = "chromium-icu-" + revision,
    )

    # Upstream Bazel packages cover a subset, not the captured Electron graph.
    for directory in ["source/common", "source/i18n", "source/stubdata"]:
        ctx.delete(directory + "/BUILD.bazel")
        ctx.delete(directory + "/BUILD")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))
    ctx.file("source_provenance.json", json.encode({"revision": revision, "integrity": integrity, "dependency": "src/third_party/icu"}))

electron_icu_repository = repository_rule(
    implementation = _impl,
    attrs = {"chromium": attr.label(mandatory = True), "build_file": attr.label(default = Label("//source:icu.BUILD.bazel"))},
)
