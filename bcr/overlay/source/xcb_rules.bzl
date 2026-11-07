load("@bazel_skylib//rules:expand_template.bzl", "expand_template")
load("@electron//electron:source_action.bzl", "electron_source_action")
load("@rules_cc//cc:cc_library.bzl", "cc_library")

EXTENSIONS = [
    "bigreq",
    "composite",
    "damage",
    "dbe",
    "dpms",
    "dri2",
    "dri3",
    "ge",
    "glx",
    "present",
    "randr",
    "record",
    "render",
    "res",
    "screensaver",
    "shape",
    "shm",
    "sync",
    "xc_misc",
    "xevie",
    "xf86dri",
    "xfixes",
    "xinerama",
    "xinput",
    "xkb",
    "xprint",
    "xproto",
    "xselinux",
    "xtest",
    "xv",
    "xvmc",
]

def electron_xcb():
    _INPUTS = native.glob([
        "xcb-proto/src/*.xml",
        "xcb-proto/xcbgen/*.py",
    ]) + ["src/c_client.py"]

    for extension in EXTENSIONS:
        electron_source_action(
            name = "generate_" + extension,
            srcs = {path: path for path in _INPUTS},
            args = ["-c", "libxcb 1.17", "-l", "X Version 11", "-s", "3", "-p", "../../xcb-proto", "../../xcb-proto/src/" + extension + ".xml"],
            logical_outputs = [extension + ".c", extension + ".h"],
            out_files = [extension + ".c", extension + ".h"],
            script = "src/c_client.py",
            target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
        )

    for header in [
        "xcb.h",
        "xcbext.h",
    ]:
        electron_source_action(
            name = "copy_" + header,
            srcs = {"src/" + header: "src/" + header, "@electron//electron/private:copy_files.py": "electron/private/copy_files.py"},
            args = ["../../src/" + header, header],
            logical_outputs = [header],
            out_files = [header],
            script = "electron/private/copy_files.py",
        )

    expand_template(
        name = "config_h",
        out = "src/config.h",
        substitutions = {
            "{LIBXCB_VERSION}": "1.17.0",
            "{LIBXCB_VERSION_MAJOR}": "1",
            "{LIBXCB_VERSION_MINOR}": "17",
            "{LIBXCB_VERSION_PATCH}": "0",
            "#define HAVE_SOCKADDR_SUN_LEN 1": "/* #undef HAVE_SOCKADDR_SUN_LEN */",
            "/* #undef HAVE_ABSTRACT_SOCKETS */": "#define HAVE_ABSTRACT_SOCKETS 1",
        },
        template = "src/config.h.in",
    )

    cc_library(
        name = "libxcb",
        srcs = [extension + ".c" for extension in EXTENSIONS] + ["src/" + name for name in [
            "xcb_auth.c",
            "xcb_conn.c",
            "xcb_ext.c",
            "xcb_in.c",
            "xcb_list.c",
            "xcb_out.c",
            "xcb_xid.c",
            "xcb_util.c",
            "xcbint.h",
            "xcb.h",
            "xcbext.h",
        ]] + [":config_h"],
        hdrs = [
            "xcb.h",
            "xcbext.h",
        ] + [extension + ".h" for extension in EXTENSIONS],
        copts = ["-DHAVE_CONFIG_H"],
        include_prefix = "xcb",
        includes = ["src"],
        target_compatible_with = [
            "@platforms//os:linux",
            "@platforms//cpu:x86_64",
        ],
        deps = ["@libxau"],
    )
