# SPDX-License-Identifier: MIT
"""Capture original Linux graphics, Blink/content targets and declared generators."""

import argparse
import ast
import gzip
import hashlib
import json
import os
import posixpath
import re
import xml.etree.ElementTree as ElementTree
from functools import cache
from pathlib import Path

from capture_mojo import SCRIPTS as MOJO_SCRIPTS
from capture_node_tools import capture as capture_node_tools
from native_graph import BUILD, capture_library, load_profiles, pack_profile

BLINK_BINDINGS_ROOTS = ["//third_party/blink/renderer/bindings:web_idl_database", "//third_party/blink/renderer/bindings:generate_bindings_all", "//third_party/blink/renderer/core:core_event_interfaces", "//third_party/blink/renderer/modules:modules_event_interfaces"]
BLINK_PLATFORM_GENERATORS = ['//third_party/blink/common:make_generated_document_policy_features', '//third_party/blink/common:make_generated_features', '//third_party/blink/common:make_generated_origin_trials', '//third_party/blink/common:make_runtime_feature_state_contexts_impl', '//third_party/blink/public/common:make_generated_permissions_policy_helper', '//third_party/blink/public/common:make_runtime_feature_state_contexts_headers', '//third_party/blink/public/mojom/origin_trials:generate_origin_trial_feature', '//third_party/blink/public/mojom/runtime_feature_state:generate_runtime_feature', '//third_party/blink/public:runtime_features_for_public', '//third_party/blink/renderer/core:make_core_generated_settings', '//third_party/blink/renderer/platform/loader:make_platform_loader_generated_delivery_type_names', '//third_party/blink/renderer/platform/loader:make_platform_loader_generated_fetch_initiator_type_names', '//third_party/blink/renderer/platform/network:http_names', '//third_party/blink/renderer/platform:color_data', '//third_party/blink/renderer/platform:font_family_names', '//third_party/blink/renderer/platform:runtime_enabled_features', '//third_party/blink/renderer/platform:runtime_feature_state_override_context']
PLATFORM_ROOTS = ["//ui/ozone:ozone", "//ui/gl:gl", "//gpu/command_buffer/client:gles2_implementation", "//gpu/command_buffer/service:gles2", "//components/viz/common:common", "//gpu/ipc/service:service", "//gpu/ipc/client:client", "//gpu/ipc/host:host", "//media:media", "//cc:cc", "//third_party/blink/renderer/platform:platform"] + BLINK_BINDINGS_ROOTS + BLINK_PLATFORM_GENERATORS
CORE_ROOTS = PLATFORM_ROOTS + ["//third_party/blink/renderer/core:core"]
DEVTOOLS_ROOT = "//third_party/devtools-frontend/src:devtools_frontend_resources"
CONTENT_METADATA = {"chromium_git_revision": "//build/util:chromium_git_revision", "tracing_config_proto": "//content/browser/resources/traces_internals:config_proto_gen"}
CONTENT_RESOURCES = {
    "download_file_types": "//components/safe_browsing/content/resources:make_file_types_protobuf",
    "ssl_error_assistant": "//components/resources/ssl/ssl_error_assistant:make_ssl_error_assistant_protobuf",
}
CONTENT_PROTO_HEADER_ACTIONS = {
    "//components/safe_browsing/content/common/proto:download_file_types_proto_gen",
    "//components/security_interstitials/content:proto_gen",
}
CONTENT_PROTO_RUNTIME_COPIES = ["//third_party/protobuf:copy_google_protobuf", "//third_party/protobuf:copy_google_protobuf_internal"]
CONTENT_WEB_ASSETS = {
    "about_tracing": "//third_party/catapult/tracing:generate_about_tracing",
    "mojo_bindings_lite": "//mojo/public/js:bindings_lite",
    "devtools_resource_manifest": "//third_party/devtools-frontend/src:generate_devtools_grd",
}
CONTENT_GENERATORS = {
    "ct_log_list": "//components/certificate_transparency/data:ct_log_list",
    "domain_reliability": "//components/domain_reliability:bake_in_configs",
    "model_descriptors": "//components/optimization_guide/core:on_device_model_execution_proto_generator",
    "policy_templates": "//components/policy:generate_policy_templates",
    "policy_source": "//components/policy:policy_code_generate",
    "component_icons": "//components/vector_icons:components_vector_icons",
    "touch_icons": "//ui/touch_selection/vector_icons:touch_selection_vector_icons",
    "window_icons": "//ui/views/window/vector_icons:window_control_vector_icons",
    "view_icons": "//ui/views:views_vector_icons",
    "blink_file_list": "//third_party/blink/renderer/bindings:check_generated_file_list",
    "blink_idl_validation": "//third_party/blink/renderer/bindings:validate_web_idl",
    "speech_dispatcher_loader": "//third_party/speech-dispatcher:speech-dispatcher_loader",
    "bubble_histograms": "//ui/views:bubble_histograms_variant",
}
MODULE_ROOTS = CORE_ROOTS + ["//third_party/blink/renderer/modules:modules", DEVTOOLS_ROOT] + list(CONTENT_METADATA.values()) + list(CONTENT_RESOURCES.values()) + list(CONTENT_WEB_ASSETS.values()) + list(CONTENT_GENERATORS.values())
CONTENT_ROOTS = MODULE_ROOTS + ["//content:content"]
ELECTRON_GENERATORS = {
    "fuses": "//electron:electron_fuses",
    "node_defines": "//electron:electron_generate_node_defines",
    "version_args": "//electron:electron_version_args",
    "version_header": "//electron:electron_version_header",
    "windows_version_resource": "//electron:electron_win_rc",
}
NPM_PREFLIGHT = "//electron:npm_pre_flight_electron_version_args"
ELECTRON_PLATFORM_ROOTS = ["//electron:electron_gtk_stubs", "//electron:libnotify_loader"]
API_SCRIPTS = {"//tools/json_schema_compiler/compiler.py", "//tools/json_schema_compiler/feature_compiler.py"}
ELECTRON_RESOURCE_ROOT = "//electron:packed_resources"
ROOTS = CONTENT_ROOTS + ELECTRON_PLATFORM_ROOTS + list(ELECTRON_GENERATORS.values()) + [ELECTRON_RESOURCE_ROOT]
SOURCE_PREFIXES = ["third_party/dom_distiller_js/dist", "third_party/readability/src", "third_party/libyuv", "third_party/angle", "third_party/dawn", "third_party/swiftshader", "third_party/spirv-tools/src", "third_party/spirv-headers/src", "third_party/vulkan-loader/src", "third_party/vulkan-tools/src", "third_party/vulkan-utility-libraries/src", "third_party/vulkan-headers/src", "third_party/vulkan_memory_allocator", "third_party/wayland/src", "third_party/wayland-protocols/src", "third_party/wayland-protocols/kde"]
MEDIA_SOURCE_PREFIXES = ["third_party/flac", "media/cdm/api", "third_party/libaom/source/libaom", "third_party/crc32c/src", "third_party/ffmpeg", "third_party/libvpx/source/libvpx", "third_party/openh264/src", "third_party/dav1d/libdav1d", "third_party/libgav1/src", "third_party/leveldatabase/src", "third_party/libwebm/source"]
COMPOSITOR_SOURCE_PREFIXES = ["third_party/webrtc", "third_party/federated_compute/src", "third_party/libsrtp"]
BLINK_SOURCE_PREFIXES = ['third_party/cld_3/src', 'third_party/cpuinfo/src', 'third_party/devtools-frontend/src', 'third_party/eigen3/src', 'third_party/emoji-segmenter/src', 'third_party/farmhash/src', 'third_party/flatbuffers/src', 'third_party/fxdiv/src', 'third_party/gemmlowp/src', 'third_party/libphonenumber/dist', 'third_party/material_color_utilities/src', 'third_party/neon_2_sse/src', 'third_party/ots/src', 'third_party/pthreadpool/src', 'third_party/ruy/src', 'third_party/search_engines_data/resources', 'third_party/smhasher/src', 'third_party/tflite/src', 'third_party/xnnpack/src']
SOURCE_PREFIXES += MEDIA_SOURCE_PREFIXES + COMPOSITOR_SOURCE_PREFIXES + BLINK_SOURCE_PREFIXES
SOURCE_PREFIXES += ["third_party/cros_system_api", "third_party/perfetto", "third_party/catapult", "third_party/openscreen/src", "third_party/pdfium"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
EXTRA_NATIVE_HEADERS = {
    "//components/viz/host:host": ["//skia/ext/skia_commit_hash.h"],
    "//services/viz/privileged/mojom/compositing:compositing": ["//services/viz/privileged/cpp/renderer_settings_mojom_traits.h", "//services/viz/privileged/cpp/overlay_strategy_mojom_traits.h"],
    "//third_party/blink/renderer/platform:platform": ["//third_party/blink/renderer/core/frame/web_feature.h"],
    "//media/gpu/chromeos:chromeos": ["//chromeos/components/cdm_factory_daemon/cdm_context_for_oopvd_impl.h"],
    "//services/viz/privileged/mojom/gl:gl": ["//services/viz/privileged/cpp/context_lost_reason_traits.h"],
    "//third_party/blink/public/mojom:android_mojo_bindings": ["//components/password_manager/content/common/credential_manager_mojom_traits.h"],
    "//services/network/public/mojom:mojom_shared_storage_blink": ["//third_party/blink/renderer/modules/shared_storage/shared_storage_blink_mojom_traits.h"],
    "//media/gpu/vaapi:common": ["//third_party/libva_protected_content/va_protected_content.h"],
    "//components/signin/public/identity_manager:identity_manager": ["//components/account_manager_core/account.h"],
    "//printing/mojom:mojom": ["//printing/page_range.h"],
    "//device/bluetooth:bluetooth": ["//chromeos/constants/chromeos_features.h", "//third_party/cros_system_api/dbus/service_constants.h"],
}
SDK_LIBS = {"gdk_pixbuf-2.0", "cups", "xshmfence", "atspi", "Xcomposite", "Xdamage", "Xfixes", "Xrandr", "Xrender", "Xtst", "drm", "asound", "ffi_pic", "X11", "Xi", "Xext", "pci", "gbm", "dbus-1", "udev", "cairo", "harfbuzz", "pango-1.0", "pangocairo-1.0", "atk-1.0", "atk-bridge-2.0"}
SCRIPTS = MOJO_SCRIPTS | API_SCRIPTS | {"//" + name for name in (
    "build/write_buildflag_header.py", "build/gn_run_binary.py", "build/util/version.py",
    "components/safe_browsing/content/resources/gen_file_type_proto.py",
    "components/resources/ssl/ssl_error_assistant/gen_ssl_error_assistant_proto.py",
    "electron/build/fuses/build.py",
    "electron/build/generate_node_defines.py",
    "electron/build/generate-template.py",
    "components/certificate_transparency/tools/make_ct_known_logs_list.py",
    "components/domain_reliability/bake_in_configs.py",
    "components/optimization_guide/tools/gen_on_device_proto_descriptors.py",
    "components/policy/resources/policy_templates.py",
    "components/policy/tools/generate_policy_source.py",
    "components/vector_icons/aggregate_vector_icons.py",
    "third_party/blink/renderer/bindings/scripts/check_generated_file_list.py",
    "third_party/blink/renderer/bindings/scripts/validate_web_idl.py",
    "tools/generate_library_loader/generate_library_loader.py",
    "tools/metrics/histograms/generate_allowlist_from_histograms_file.py",
    "mojo/public/tools/bindings/concatenate-files.py",
    "mojo/public/tools/bindings/concatenate_and_replace_closure_exports.py",
    "third_party/devtools-frontend/src/scripts/build/generate_devtools_grd.py",
    "third_party/catapult/tracing/bin/generate_about_tracing_contents",
    "third_party/node/node.py",
    "third_party/devtools-frontend/src/scripts/build/assert_grd.py",
    "third_party/devtools-frontend/src/scripts/build/assert_third_party_readmes.py",
    "tools/json_to_struct/json_to_struct.py",
    "services/device/public/cpp/usb/tools/usb_ids.py",
    "third_party/devtools-frontend/src/scripts/build/typescript/ts_library.py",
    "third_party/devtools-frontend/src/scripts/build/build_inspector_overlay.py",
    "third_party/blink/renderer/bindings/scripts/collect_idl_files.py",
    "third_party/blink/renderer/bindings/scripts/build_web_idl_database.py",
    "third_party/blink/renderer/bindings/scripts/generate_bindings.py",
    "third_party/blink/renderer/bindings/scripts/generate_event_interface_names.py",
    "third_party/blink/renderer/build/scripts/generate_permission_element_grd.py",
    "third_party/blink/renderer/build/scripts/make_html_entity_table.py",
    "third_party/blink/renderer/build/scripts/make_instrumenting_probes.py",
    "third_party/blink/renderer/core/sanitizer/builtins_generate_config.py",
    "third_party/inspector_protocol/check_protocol_compatibility.py",
    "third_party/inspector_protocol/code_generator.py",
    "third_party/inspector_protocol/concatenate_protocols.py",
    "tools/grit/grit.py", "tools/grit/pak_util.py", "tools/variations/fieldtrial_to_struct.py",
    "tools/metrics/private_metrics/gen_builders.py", "tools/metrics/ukm/gen_builders.py",
    "third_party/blink/renderer/build/scripts/run_with_pythonpath.py",
    "third_party/webrtc/experiments/field_trials.py",
    "gpu/config/process_json.py", "tools/protoc_wrapper/protoc_wrapper.py", "tools/generate_stubs/generate_stubs.py",
    "third_party/wayland/wayland_scanner_wrapper.py",
    "third_party/spirv-tools/src/utils/generate_language_headers.py",
    "third_party/spirv-tools/src/utils/generate_registry_tables.py",
    "third_party/spirv-tools/src/utils/ggt.py",
    "third_party/swiftshader/third_party/SPIRV-Tools/utils/generate_language_headers.py",
    "third_party/swiftshader/third_party/SPIRV-Tools/utils/generate_registry_tables.py",
    "third_party/swiftshader/third_party/SPIRV-Tools/utils/ggt.py",
    "third_party/swiftshader/src/Vulkan/write_icd_json.py",
    "third_party/dawn/generator/extract_json.py",
    "third_party/dawn/generator/opengl_loader_generator.py",
    "third_party/dawn/generator/dawn_json_generator.py",
    "third_party/vulkan-tools/src/scripts/gn/generate_vulkan_icd_json.py",
    "net/tools/dafsa/make_dafsa.py", "third_party/angle/src/commit_id.py",
    "third_party/angle/src/program_serialize_data_version.py",
    "ui/ozone/generate_constructor_list.py", "ui/ozone/generate_ozone_platform_list.py",
)}


def source_files(root):
    for directory, children, filenames in os.walk(root, followlinks=True):
        children[:] = sorted(name for name in children if name not in (".git", "__pycache__"))
        for name in sorted(filenames):
            yield Path(directory) / name



def grit_resource_inputs(inputs, physical):
    pending = [(path[2:], None) for path in inputs if path.startswith("//") and not path.startswith(BUILD) and path.endswith((".grd", ".grdp"))]
    seen, resources = set(), set()
    asset_types = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".cur", ".woff", ".woff2", ".ttf", ".json", ".bin"}
    while pending:
        source, base = pending.pop()
        if (source, base) in seen or not physical(source).is_file():
            continue
        seen.add((source, base))
        tree = ElementTree.parse(physical(source))
        if base is None:
            base = posixpath.normpath(posixpath.join(posixpath.dirname(source), tree.getroot().attrib.get("base_dir", ".")))
        for node in tree.iter():
            name = node.attrib.get("file") or (node.attrib.get("path") if node.tag == "file" else None)
            if not name or any(marker in name for marker in ("$", "<(", "%(")):
                continue
            if node.attrib.get("type") == "chrome_scaled_image":
                for layout in physical(base).iterdir():
                    if layout.is_dir() and re.search(r"_\d+_percent$", layout.name):
                        variant = posixpath.normpath(posixpath.join(base, layout.name, name))
                        if not variant.startswith(("/", "../")) and physical(variant).is_file():
                            resources.add("//" + variant)
                continue
            path = posixpath.normpath(posixpath.join(base, name))
            if path.startswith(("/", "../")) or not physical(path).is_file():
                continue
            resources.add("//" + path)
            if path.endswith((".grd", ".grdp")):
                pending.append((path, base))
            elif Path(path).suffix in (".html", ".css", ".js"):
                directory = posixpath.dirname(path)
                root = physical(directory)
                resources.update("//" + directory + "/" + asset.relative_to(root).as_posix() for asset in source_files(root) if asset.is_file() and asset.suffix in asset_types)
    pending = [path for path in resources if path.endswith((".html", ".js", ".css"))]
    visited = set()
    while pending:
        source = pending.pop()
        if source in visited:
            continue
        visited.add(source)
        for include in re.findall(r'<include\b[^>]*\bsrc=["\']([^"\']+)["\']', physical(source[2:]).read_text(), re.I):
            path = posixpath.normpath(posixpath.join(posixpath.dirname(source[2:]), include))
            if path.startswith(("/", "../")) or not physical(path).is_file():
                continue
            original = "//" + path
            resources.add(original)
            if path.endswith((".html", ".js", ".css", ".svg")):
                pending.append(original)
    return resources


def flatbuffer_schema_inputs(inputs, physical):
    pending = [path[2:] for path in inputs if path.startswith("//") and not path.startswith(BUILD) and path.endswith(".fbs")]
    seen, resources = set(), set()
    while pending:
        source = pending.pop()
        if source in seen:
            continue
        seen.add(source)
        for name in re.findall(r'^\s*include\s+"([^"\n]+)"\s*;', physical(source).read_text(), re.M):
            candidates = [posixpath.normpath(posixpath.join(posixpath.dirname(source), name)), posixpath.normpath(name)]
            path = next((path for path in candidates if not path.startswith(("/", "../")) and physical(path).is_file()), None)
            if path is None:
                raise ValueError("Missing original FlatBuffers include: " + name)
            resources.add("//" + path)
            pending.append(path)
    return resources


def source_revisions(chromium):
    def read_deps(path):
        tree = ast.parse(path.read_text())
        assignments = {name.id: node.value for node in tree.body if isinstance(node, ast.Assign) for name in node.targets if isinstance(name, ast.Name)}
        variables = {key.value: value for key, value in zip(assignments["vars"].keys, assignments["vars"].values) if isinstance(key, ast.Constant)}
        entries = {key.value: value for key, value in zip(assignments["deps"].keys, assignments["deps"].values) if isinstance(key, ast.Constant)}
        return variables, entries

    variables, entries = read_deps(chromium / "DEPS")

    def text(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return text(node.left) + text(node.right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Var" and len(node.args) == 1 and not node.keywords:
            return text(variables[ast.literal_eval(node.args[0])])
        raise ValueError("Unsupported source pin expression")

    records = {}
    def record(prefix, node):
        if isinstance(node, ast.Dict):
            node = next(value for key, value in zip(node.keys, node.values) if isinstance(key, ast.Constant) and key.value == "url")
        url = text(node).replace("{chromium_git}", text(variables["chromium_git"]))
        remote, commit = url.rsplit("@", 1)
        if not remote.startswith("https://") or not re.fullmatch("[0-9a-f]{40}", commit):
            raise ValueError("Invalid exact platform source revision")
        records[prefix] = dict(remote=remote, commit=commit)
        if prefix == "third_party/catapult":
            if commit != "04c85a1d0e324464c6be4b3d193b47cb6177d03a":
                raise ValueError("Update exact Catapult archive metadata")
            records[prefix]["archive"] = {
                "url": "https://codeload.github.com/catapult-project/catapult/tar.gz/" + commit,
                "sha256": "5a57259f90c4cba3636b25989dd8e513fc13fa7f12364dc156e0c62cd873cee0",
                "strip_prefix": "catapult-" + commit,
            }

    for prefix in SOURCE_PREFIXES:
        record(prefix, entries["src/" + prefix])
    variables, entries = read_deps(chromium / "third_party/dawn/DEPS")
    for prefix in ["third_party/khronos/EGL-Registry", "third_party/khronos/OpenGL-Registry"]:
        record("third_party/dawn/" + prefix, entries[prefix])
    for group, prefix in [("ffmpeg", "third_party/ffmpeg"), ("webrtc", "third_party/webrtc"), ("devtools_frontend", "third_party/devtools-frontend/src"), ("perfetto", "third_party/perfetto")]:
        records[prefix]["patch_group"] = group
    return records


def capture(graph, digest, chromium, source_roots, profiles):
    revisions = source_revisions(chromium)
    previous = [("base", "base"), ("embedder", "embedder"), ("ipcz", "ipcz"), ("libnode", "libnode"), ("perfetto", "perfetto_native"), ("protobuf", "protobuf"), ("v8_engine", "v8_engine"), ("v8_support", "v8_support"), ("network", "network"), ("mojo", "mojo"), ("fonts", "fonts"), ("codecs", "codecs"), ("skia", "skia"), ("gfx", "gfx"), ("display", "display"), ("events", "events"), ("ui", "ui"), ("content_webui", "content_webui")]
    external, shared = load_profiles(profiles, previous)
    external = {label: owner for label, owner in external.items() if not owner.startswith("@electron_platform_sources//:")}
    shared[BUILD + "icudtl.dat"] = "@electron_icu_sources//:common/icudtl.dat"
    shared["//v8/include/js_protocol-1.3.json"] = "@electron_v8_sources//:include/js_protocol-1.3.json"
    external["//media/filters:symphonia_glue"] = "@electron//source/media:symphonia"
    external["//media/filters:symphonia_glue_cxx_generated"] = "@electron//source/media:symphonia_bridge"
    temporal = json.loads((profiles / "temporal_inputs.json").read_text())
    for label, crate in temporal["rust"].items():
        if crate["kind"] in ("rust_library", "executable"):
            external.setdefault(label, "@electron_rust_sources//:" + crate["name"])
    for label in ("//base/allocator/partition_allocator:partition_alloc", "//base/allocator/partition_allocator/src/partition_alloc:partition_alloc"):
        external[label] = "@electron_partition_alloc_sources//:partition_alloc"
    for name, library in temporal.get("content_libraries", {}).items():
        external[library["root"]] = "@electron_rust_sources//:" + name
    for name, bridge in temporal["blink_bridges"].items():
        owner = "@electron//source/blink_rust:" + name
        external[bridge["root"]] = owner
        external[bridge["root"] + "_cxx_generated"] = owner + "_bridge"
        for output in bridge["outputs"]:
            shared[BUILD + output] = "@electron//source/blink_rust:" + output
        if bridge.get("helper"):
            external[bridge["helper"]["gn_target"]] = owner + "_cpp"
    external["//third_party/crabbyavif:crabbyavif"] = "@electron//source/crabbyavif:crabbyavif"
    external["//third_party/crabbyavif:header_files"] = "@electron_rust_sources//:crabbyavif_headers"
    targets = graph["targets"]
    node_lock = json.loads((profiles / "node_tools_lock.json").read_text())
    if capture_node_tools(source_roots.get("electron", chromium / "electron")) != node_lock:
        raise ValueError("Electron Node tool closure differs from original Yarn metadata")
    package = json.loads((source_roots.get("electron", chromium / "electron") / "package.json").read_text())
    if package["scripts"]["generate-version-json"] != "node script/generate-version-json.js":
        raise ValueError("Original Electron version entry point changed")
    if targets[NPM_PREFLIGHT]["inputs"] != ["//electron/package.json", "//electron/yarn.lock"]:
        raise ValueError("Original Electron npm preflight inputs changed")

    app_seen, app_pending = set(), ["//electron:electron_app"]
    while app_pending:
        label = app_pending.pop()
        if label in app_seen or label in TOOLCHAIN:
            continue
        app_seen.add(label)
        app_pending.extend(targets[label].get("deps", []))
    api_generators = sorted(label for label in app_seen if targets[label].get("script") in API_SCRIPTS)
    capture_roots = ROOTS + api_generators

    def closure(roots):
        seen, pending = set(), list(roots)
        while pending:
            label = pending.pop()
            if label in seen or label in external or label in TOOLCHAIN or label == NPM_PREFLIGHT:
                continue
            seen.add(label)
            pending.extend(targets[label].get("deps", []))
        return seen

    platform_seen, core_seen, module_seen, content_seen, seen = closure(PLATFORM_ROOTS), closure(CORE_ROOTS), closure(MODULE_ROOTS), closure(CONTENT_ROOTS), closure(capture_roots)
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}

    def physical(path):
        for prefix, root in sorted(source_roots.items(), key=lambda item: -len(item[0])):
            if path == prefix or path.startswith(prefix + "/"):
                return root / path[len(prefix):].lstrip("/")
        return chromium / path

    @cache
    def source_includes(source):
        text = physical(source).read_text(encoding="utf-8", errors="surrogateescape")
        implementations = re.findall(r'^\s*#\s*include\s*["<]([^"\n>]+\.(?:c|cc|cpp))[">]', text, re.M)
        quoted = re.findall(r'^\s*#\s*include\s*"([^"\n]+)"', text, re.M)
        return implementations, quoted

    hook_label = "//gpu/webgpu:checkout_lastchange_dawn"
    hook_name = "checkout_lastchange_dawn"
    hook_outputs = [BUILD + "src/gpu/webgpu/" + name for name in ["DAWN_VERSION", "dawn_commit_hash.h"]]
    source_aliases = {"//gpu/webgpu/" + path.rsplit("/", 1)[-1]: path for path in hook_outputs}
    dawn = revisions["third_party/dawn"]["commit"]
    if dawn != "cee9cb0d67e749bf42f5e90cb3b8a6f525dbb920":
        raise ValueError("Update pinned Dawn checkout-hook commit metadata")
    tree = ast.parse((chromium / "DEPS").read_text())
    hook_list = next(node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(name, ast.Name) and name.id == "hooks" for name in node.targets))
    hook = next(node for node in hook_list.elts if isinstance(node, ast.Dict) and any(isinstance(key, ast.Constant) and key.value == "name" and isinstance(value, ast.Constant) and value.value == "lastchange_dawn" for key, value in zip(node.keys, node.values)))
    original_command = ast.literal_eval(next(value for key, value in zip(hook.keys, hook.values) if isinstance(key, ast.Constant) and key.value == "action"))
    expected_command = ["python3", "src/build/util/lastchange.py", "-m", "DAWN_COMMIT_HASH", "-s", "src/third_party/dawn", "--revision", "src/gpu/webgpu/DAWN_VERSION", "--header", "src/gpu/webgpu/dawn_commit_hash.h"]
    if original_command != expected_command:
        raise ValueError("Original Dawn checkout hook changed")
    names[hook_label] = hook_name
    skia = json.loads((profiles / "skia_inputs.json").read_text())["source_revisions"]["skia"]
    if skia != "f4ed99d2443962782cf5f8b4dd27179f131e7cbe":
        raise ValueError("Update pinned Skia checkout-hook commit metadata")
    skia_hook = next(node for node in hook_list.elts if isinstance(node, ast.Dict) and any(isinstance(key, ast.Constant) and key.value == "name" and isinstance(value, ast.Constant) and value.value == "lastchange_skia" for key, value in zip(node.keys, node.values)))
    skia_command = ast.literal_eval(next(value for key, value in zip(skia_hook.keys, skia_hook.values) if isinstance(key, ast.Constant) and key.value == "action"))
    if skia_command != ["python3", "src/build/util/lastchange.py", "-m", "SKIA_COMMIT_HASH", "-s", "src/third_party/skia", "--header", "src/skia/ext/skia_commit_hash.h"]:
        raise ValueError("Original Skia checkout hook changed")
    skia_hook_label = "//skia:checkout_lastchange_skia"
    skia_hook_name = "checkout_lastchange_skia"
    skia_outputs = [BUILD + "src/skia/ext/skia_commit_hash.h"]
    names[skia_hook_label] = skia_hook_name
    source_aliases["//skia/ext/skia_commit_hash.h"] = skia_outputs[0]
    files, generated, headers, used_shared = set(), {}, {}, set()
    literal_metadata = {}
    producers = {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "action_foreach", "generated_file", "copy"):
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate platform output")
                producers[output] = label
    producers.update({path: hook_label for path in hook_outputs})
    producers.update({path: skia_hook_label for path in skia_outputs})
    tools = {output: label for label, target in targets.items() if target["type"] == "executable" and (label in seen or label in external) for output in target.get("outputs", [])[:1]}
    tools[BUILD + "gperf"] = "@gperf//:gperf"
    node = "//third_party/node/linux/node-linux-x64/bin/node"
    esbuild = "//third_party/devtools-frontend/src/third_party/esbuild/esbuild"
    tools[node] = "@electron_chromium_node_tool//:node-linux-x64/bin/node"
    tools[esbuild] = "@electron_platform_esbuild//:esbuild"
    execution_closure, pending = set(), [label for label in seen if targets[label]["type"] == "executable"]
    while pending:
        label = pending.pop()
        if label in execution_closure or label not in seen:
            continue
        execution_closure.add(label)
        pending.extend(targets[label].get("deps", []))

    def input_file(path):
        if path in source_aliases:
            return
        if path in tools:
            return
        if path in generated:
            return
        if path in shared:
            used_shared.add(path)
        elif path.startswith(BUILD):
            if path in graph["generated_files"]:
                generated[path] = graph["generated_files"][path]
            elif path not in producers:
                raise ValueError("Unowned platform input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Invalid platform source path")

    directories = ["services/viz/public", "third_party/libyuv", "gpu", "components/viz/common", "third_party/khronos", "ui", "dbus", "components/dbus", "components/url_formatter", "components/headless", "services/service_manager/public", "third_party/angle", "third_party/dawn", "third_party/swiftshader", "third_party/spirv-tools/src", "third_party/spirv-headers/src", "third_party/vulkan-loader/src", "third_party/vulkan-tools/src", "third_party/vulkan-utility-libraries/src", "third_party/vulkan-headers/src", "third_party/wayland/src", "third_party/wayland/include"]
    media_header_roots = ["media", "third_party/libaom", "third_party/crc32c", "third_party/ffmpeg", "third_party/flac", "third_party/opus", "third_party/libvpx", "third_party/openh264", "third_party/dav1d", "third_party/libgav1", "third_party/leveldatabase", "third_party/libwebm"]
    directories.append("third_party/eigen3/src")
    directories += media_header_roots
    directories += [path for path in MEDIA_SOURCE_PREFIXES if path not in directories]
    def header_directories(labels):
        selected, implicit = list(directories), set()
        for label in sorted(labels):
            if targets[label]["type"] not in ("source_set", "static_library", "shared_library", "executable"):
                continue
            if label in {producer.removesuffix("_gen") for producer in CONTENT_PROTO_HEADER_ACTIONS}:
                if not targets[label].get("sources") or any(not path.startswith(BUILD) for path in targets[label]["sources"]):
                    raise ValueError("Scoped protobuf library gained original native sources: " + label)
                continue
            directory = label[2:].rsplit(":", 1)[0]
            if not directory or any(directory == root or directory.startswith(root + "/") for root in selected):
                continue
            selected.append(directory)
            implicit.add(directory)
        return selected, implicit

    platform_directories, platform_implicit = header_directories(platform_seen)
    core_directories, core_implicit = header_directories(core_seen)
    core_directories = platform_directories + [path for path in core_directories if path not in platform_directories]
    module_directories, module_implicit = header_directories(module_seen)
    module_directories = core_directories + [path for path in module_directories if path not in core_directories]
    content_directories, content_implicit = header_directories(content_seen)
    content_directories = module_directories + [path for path in content_directories if path not in module_directories]
    all_directories, implicit_header_roots = header_directories(seen)
    directories = content_directories + [path for path in all_directories if path not in content_directories]
    implicit_header_roots.update(platform_implicit | core_implicit | module_implicit | content_implicit)
    assembly_inputs = {}
    for directory in directories:
        root = physical(directory)
        roots = [(directory, root)] + [(prefix, checkout) for prefix, checkout in source_roots.items() if prefix.startswith(directory + "/")]
        inventory = sorted({prefix + "/" + path.relative_to(checkout).as_posix() for prefix, checkout in roots for path in source_files(checkout) if path.is_file() and (path.suffix in (".h", ".hh", ".hpp", ".hpp11", ".inc", ".inl", ".def", ".gen") or (prefix == "third_party/eigen3/src" and not path.suffix and path.relative_to(checkout).as_posix().startswith(("Eigen/", "unsupported/Eigen/"))))})
        if not inventory and directory not in media_header_roots and directory not in implicit_header_roots:
            raise ValueError("Missing original platform header inventory: " + directory)
        headers[directory] = inventory
        if directory.startswith(tuple("third_party/" + name for name in ["libaom", "ffmpeg", "libvpx", "openh264", "dav1d"])):
            project = "/".join(directory.split("/")[:2])
            assembly_inputs.setdefault(project, set()).update("//" + path for path in inventory)
            assembly_inputs[project].update("//" + directory + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.is_file() and path.suffix == ".asm")
        for path in inventory:
            input_file("//" + path)

    headers["khronos_exports"] = ["gpu/command_buffer/client/gles2_c_lib_export.h"]
    for path in headers["khronos_exports"]:
        input_file("//" + path)

    # Public interfaces referenced by patched content and generated Mojo code.
    content_interfaces = [
        "components/password_manager/content/common/credential_manager_mojom_traits.h",
        "components/password_manager/core/common/credential_manager_types.h",
        "components/reporting/util/encrypted_reporting_json_keys.h",
        "electron/shell/browser/ui/file_dialog.h",
    ]
    puffin = "third_party/puffin/src/include"
    content_interfaces += sorted(puffin + "/" + path.relative_to(physical(puffin)).as_posix() for path in source_files(physical(puffin)) if path.is_file() and path.suffix == ".h")
    if not any(path.endswith("/puffpatch.h") for path in content_interfaces):
        raise ValueError("Missing original Puffin public headers")
    for path in content_interfaces:
        input_file("//" + path)

    def dependency_inputs(label):
        paths, visited, pending = set(), set(), list(targets[label].get("deps", []))
        while pending:
            dependency = pending.pop()
            if dependency in visited or dependency == NPM_PREFLIGHT:
                continue
            visited.add(dependency)
            target = targets[dependency]
            if target["type"] in ("action", "action_foreach", "copy", "generated_file"):
                paths.update(target.get("outputs", []))
                paths.update(target.get("inputs", []))
                paths.update(target.get("sources", []))
            elif target["type"] != "group":
                continue
            pending.extend(target.get("deps", []))
        return paths

    devtools_deps = ast.parse(physical("third_party/devtools-frontend/src/DEPS").read_text())
    devtools_entries = next(node.value for node in devtools_deps.body if isinstance(node, ast.Assign) and any(isinstance(name, ast.Name) and name.id == "deps" for name in node.targets))
    esbuild_entry = ast.literal_eval(next(value for key, value in zip(devtools_entries.keys, devtools_entries.values) if isinstance(key, ast.Constant) and key.value == "third_party/esbuild"))
    if esbuild_entry["packages"] != [{"package": "infra/3pp/tools/esbuild/${{platform}}", "version": "version:3@0.25.1.chromium.2"}]:
        raise ValueError("Update exact DevTools esbuild package pin")
    devtools_esbuild = dict(url="https://chrome-infra-packages.appspot.com/dl/infra/3pp/tools/esbuild/linux-amd64/+/version:3@0.25.1.chromium.2", sha256="520554b1c0ad045201310582a01ef7a0ba9b5d033d8f03a709c369c52f81d9c9", source="third_party/devtools-frontend/src/DEPS", packages=esbuild_entry["packages"])
    devtools_modules = "third_party/devtools-frontend/src/node_modules"
    devtools_packages = sorted(devtools_modules + "/" + path.relative_to(physical(devtools_modules)).as_posix() for path in source_files(physical(devtools_modules)) if path.is_file() and path.name not in ("BUILD", "BUILD.bazel"))
    if not devtools_packages:
        raise ValueError("Missing original DevTools npm inventory")
    files.update(devtools_packages)
    workspace_script = "third_party/devtools-frontend/src/scripts/build/generate_devtools_json.js"
    workspace_source = physical(workspace_script).read_text()
    workspace_substitutions = {
        "const [, , outputLocation] = process.argv;": "const [, , outputLocation, workspaceRoot] = process.argv;",
        "const root = path.join(path.dirname(path.dirname(__dirname)), 'front_end');": "const root = workspaceRoot ?? path.join(path.dirname(path.dirname(__dirname)), 'front_end');",
    }
    if any(workspace_source.count(before) != 1 for before in workspace_substitutions):
        raise ValueError("Original DevTools workspace generator changed")
    devtools_workspace = dict(target="//third_party/devtools-frontend/src/front_end:devtools_json", script=workspace_script, source_sha256=hashlib.sha256(workspace_source.encode()).hexdigest(), root="/src/third_party/devtools-frontend/src/front_end", substitutions=workspace_substitutions)
    devtools_scripts = "third_party/devtools-frontend/src/scripts"
    devtools_javascript = sorted("//" + devtools_scripts + "/" + path.relative_to(physical(devtools_scripts)).as_posix() for path in source_files(physical(devtools_scripts)) if path.suffix in (".js", ".mjs", ".cjs", ".json"))
    actions, libraries, metadata, copies = {}, {}, {}, {}
    ml_dtypes_headers = []
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 platform profile")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind in ("action", "action_foreach"):
            if target["script"] not in SCRIPTS and label != ELECTRON_GENERATORS["version_args"]:
                raise ValueError("Untranslated platform generator: " + target["script"])
            if label in CONTENT_PROTO_HEADER_ACTIONS or label in CONTENT_GENERATORS.values():
                record["scoped_native_headers"] = True
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [target["script"]]) | dependency_inputs(label)
            if label in CONTENT_RESOURCES.values():
                generators = [dep + "_gen" for dep in target.get("deps", []) if dep + "_gen" in CONTENT_PROTO_HEADER_ACTIONS]
                if len(generators) != 1:
                    raise ValueError("Expected one original resource protobuf provider: " + label)
                modules = [output for output in targets[generators[0]]["outputs"] if output.endswith("_pb2.py")]
                if len(modules) != 1:
                    raise ValueError("Expected one generated resource Python module: " + label)
                inputs.update(modules)
                record["generated_proto_inputs"] = modules
            if target["script"] == "//components/vector_icons/aggregate_vector_icons.py" and any(arg.startswith("--output_test_h") for arg in target.get("args", [])):
                directory = next(arg.split("=", 1)[1] for arg in target["args"] if arg.startswith("--working_directory="))
                if not directory.startswith("../../"):
                    raise ValueError("Untranslated icon template directory")
                inputs.add("//" + directory[6:] + "/vector_icons_unittest.h.template")
            if label == CONTENT_GENERATORS["model_descriptors"]:
                for runtime in CONTENT_PROTO_RUNTIME_COPIES:
                    inputs.update(targets[runtime]["sources"])
            if label == CONTENT_GENERATORS["policy_templates"]:
                for directory, suffixes in [("components/policy/resources/templates", (".yaml",)), ("third_party/pyyaml", (".py",))]:
                    root = physical(directory)
                    paths = ["//" + directory + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.suffix in suffixes]
                    if not paths:
                        raise ValueError("Missing pinned policy inputs: " + directory)
                    inputs.update(paths)
            if target["script"] == "//tools/grit/grit.py":
                inputs.update(grit_resource_inputs(inputs, physical))
            script_parent = physical(target["script"][2:]).parent
            for path in script_parent.glob("*.py"):
                inputs.add(target["script"].rsplit("/", 1)[0] + "/" + path.name)
            helper_directories = []
            if label == CONTENT_WEB_ASSETS["about_tracing"]:
                asset_types = (".js", ".html", ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".ttf", ".otf", ".eot")
                for directory in ("third_party/catapult/tracing/tracing", "third_party/catapult/third_party/polymer", "third_party/catapult/tracing/third_party"):
                    root = physical(directory)
                    assets = ["//" + directory + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.suffix in asset_types]
                    if not assets:
                        raise ValueError("Missing pinned tracing asset inventory: " + directory)
                    inputs.update(assets)
                helper_directories += ["third_party/catapult/" + path for path in (
                    "tracing/tracing_build",
                    "third_party/beautifulsoup4-4.9.3/py3k/bs4",
                    "third_party/html5lib-1.1/html5lib",
                    "third_party/webencodings-0.5.1/webencodings",
                    "third_party/six",
                )]
            if label in CONTENT_RESOURCES.values():
                helper_directories.append("components/resources/protobufs")
            if target["script"] in API_SCRIPTS:
                helper_directories += ["tools/json_schema_compiler", "tools/json_comment_eater", "tools/idl_parser", "third_party/ply"]
            if target["script"].startswith("//tools/grit/") or target["script"] == "//third_party/blink/renderer/build/scripts/generate_permission_element_grd.py":
                helper_directories.append("tools/grit")
            if target["script"].startswith("//tools/metrics/"):
                helper_directories += ["tools/metrics/common", "tools/metrics/ukm", "tools/metrics/private_metrics"]
            if target["script"] == "//third_party/blink/renderer/build/scripts/make_instrumenting_probes.py":
                helper_directories += ["third_party/jinja2", "third_party/markupsafe", "third_party/blink/renderer/build/scripts/blinkbuild"]
                inputs.add("//third_party/blink/renderer/build/scripts/templates/macros.tmpl")
            if target["script"] == "//third_party/inspector_protocol/code_generator.py":
                for directory in ("third_party/inspector_protocol/templates", "third_party/inspector_protocol/lib"):
                    root = physical(directory)
                    inputs.update("//" + directory + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.suffix == ".template")
            if target["script"] in ("//tools/variations/fieldtrial_to_struct.py", "//tools/json_to_struct/json_to_struct.py"):
                helper_directories += ["tools/json_comment_eater", "tools/json_to_struct"]
            if target["script"] == "//tools/variations/fieldtrial_to_struct.py":
                inputs.add("//components/variations/service/generate_ui_string_overrider.py")
            for directory in helper_directories:
                root = physical(directory)
                inputs.update("//" + directory + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.suffix == ".py")
            devtools = target["script"].startswith("//third_party/devtools-frontend/src/")
            if devtools:
                inputs.update({"//third_party/node/node.py", "//third_party/node/node_modules.py", "//third_party/devtools-frontend/src/scripts/devtools_paths.py"})
                inputs.add(node)
                if target["script"].endswith("/ts_library.py"):
                    inputs.add(esbuild)
                record["devtools_node_modules"] = True
            args = [arg.replace("$SOURCE_ROOT/out/bazel-import/", "") for arg in target.get("args", [])]
            if label in ELECTRON_GENERATORS.values():
                record["gn_args"] = target.get("args", [])
                args = [arg.replace("$SOURCE_ROOT/", "../../") for arg in args]
            if label == ELECTRON_GENERATORS["version_args"]:
                if target["script"] != "//electron/build/npm-run.py" or args[:3] != ["--silent", "generate-version-json", "--"] or len(args) != 5:
                    raise ValueError("Original Electron version command changed")
                record["npm_replacement"] = dict(script=target["script"], args=target["args"], preflight=NPM_PREFLIGHT, lock="node_tools_lock.json")
                inputs.discard(target["script"])
                inputs.update(["//electron/package.json", "//electron/yarn.lock", "//third_party/node/node.py", node])
                record["mapped_source_groups"] = {"@electron_npm//:pkg_" + identity: "electron/node_modules/" + name for name, identity in node_lock["roots"].items()}
                args = ["../../electron/script/generate-version-json.js"] + args[3:]
            if target["script"] == "//tools/grit/pak_util.py" and (not args or args[0] != "repack"):
                raise ValueError("Only original resource repack actions are captured")
            if "--protoc-gen-ts" in args:
                if target["script"] != "//tools/protoc_wrapper/protoc_wrapper.py":
                    raise ValueError("Unexpected TypeScript protobuf plugin producer")
                position = args.index("--protoc-gen-ts") + 1
                plugin = "tools/protoc_wrapper/protoc-gen-ts_proto.py"
                if args[position] not in ("./../../" + plugin, "../../" + plugin):
                    raise ValueError("Original TypeScript protobuf plugin changed")
                record["gn_args"] = list(args)
                launcher = plugin.removesuffix(".py") + ".launcher"
                args[position] = "../../" + launcher
                record["python_tools"] = {launcher: plugin}
                record["webui_node_modules"] = True
                inputs.update(["//" + plugin, "//third_party/node/node.py", "//third_party/node/node_modules.py", node])
            if label == devtools_workspace["target"]:
                record["gn_args"] = list(args)
                args.append(devtools_workspace["root"])
            if target["script"] == "//third_party/node/node.py":
                if not args or not args[0].startswith("../../third_party/devtools-frontend/src/"):
                    raise ValueError("Untranslated Node generator entry point")
                entry = args[0][6:]
                inputs.update(devtools_javascript)
                inputs.add("//" + entry)
                inputs.add("//third_party/devtools-frontend/src/package.json")
                if entry.endswith("/collect-ui-strings.js"):
                    helpers = "third_party/devtools-frontend/src/third_party/i18n"
                    inputs.update("//" + helpers + "/" + path.relative_to(physical(helpers)).as_posix() for path in source_files(physical(helpers)) if path.suffix in (".js", ".json"))
                    frontend = "third_party/devtools-frontend/src/front_end"
                    inputs.update("//" + frontend + "/" + path.relative_to(physical(frontend)).as_posix() for path in source_files(physical(frontend)) if path.suffix in (".js", ".ts", ".gn"))
                inputs.add(node)
                # Frontend entry points also import local sibling helpers.
                parent = physical(entry).parent
                inputs.update("//" + entry.rsplit("/", 1)[0] + "/" + path.name for path in parent.iterdir() if path.is_file() and path.suffix in (".js", ".mjs", ".cjs", ".json"))
                builtin = entry.rsplit("/", 1)[-1] in ("copy-file.js", "copy-files.js", "generate-tsconfig.js", "minify-json-files.js")
                if not builtin:
                    record["devtools_node_modules"] = True
                    inputs.add(esbuild)
            if target["script"] == "//third_party/inspector_protocol/check_protocol_compatibility.py":
                for arg in args:
                    if not arg.startswith("../../") or not arg.endswith(".pdl"):
                        continue
                    source = arg[6:]
                    version = re.search(r"(?m)^version\s+major (\d+)\s+minor (\d+)", physical(source).read_text())
                    if not version:
                        raise ValueError("Missing original protocol version: " + source)
                    baseline = source.removesuffix(".pdl") + "-" + version[1] + "." + version[2] + ".json"
                    if not physical(baseline).is_file():
                        raise ValueError("Missing original protocol baseline: " + baseline)
                    inputs.add("//" + baseline)
            if target["script"] == "//third_party/blink/renderer/build/scripts/generate_permission_element_grd.py":
                directory = args[args.index("--input_base_dir") + 1]
                if directory != "../../third_party/blink/public/strings/":
                    raise ValueError("Untranslated permission string input root")
                inputs.add("//third_party/blink/public/strings/permission_element_strings.grd")
                translations = sorted(physical("third_party/blink/public/strings/translations").glob("permission_element_strings_*"))
                if not translations:
                    raise ValueError("Missing original permission string translations")
                inputs.update("//third_party/blink/public/strings/translations/" + path.name for path in translations if path.is_file())
            if target["script"] in ("//tools/variations/fieldtrial_to_struct.py", "//tools/json_to_struct/json_to_struct.py"):
                # Pin generated copyright to the captured release year.
                record["reproducibility_options"] = {"year": "2025", "basis": "Chromium 142 source release"}
                args.append("--year=2025")
            if "gperf" in args:
                if target["script"] != "//third_party/blink/renderer/build/scripts/run_with_pythonpath.py" or not ("../../third_party/blink/renderer/build/scripts/gperf.py" in args or "--gperf" in args):
                    raise ValueError("Unexpected original gperf invocation")
                inputs.add(BUILD + "gperf")
                args = ["./gperf" if arg == "gperf" else arg for arg in args]
            if target["script"] == "//build/gn_run_binary.py":
                executable = BUILD + args[0] if args else ""
                if executable not in tools:
                    raise ValueError("Untranslated original generator executable: " + executable)
                inputs.add(executable)
                if args[0] == "character_data_generator":
                    # This generator reads data beside argv[0].
                    inputs.add(BUILD + "icudtl.dat")
                if args[0] == "flatc":
                    if args[args.index("-I") + 1] != "../../":
                        raise ValueError("Untranslated original FlatBuffers include root")
                    inputs.update(flatbuffer_schema_inputs(inputs, physical))
            if target["script"] == "//build/gn_run_binary.py" and args and args[0] == "nasm":
                if "--reproducible" not in args:
                    raise ValueError("Original NASM action lacks reproducible output mode")
                projects = {"/".join(path[2:].split("/")[:2]) for path in target["sources"]}
                for project in projects:
                    inputs.update(assembly_inputs[project])
            jinja_option = "--jinja2-path" if "--jinja2-path" in args else "--jinja_dir" if "--jinja_dir" in args else None
            if jinja_option:
                package = args[args.index(jinja_option) + 1]
                if package != ("../../third_party/jinja2" if jinja_option == "--jinja2-path" else "../../third_party"):
                    raise ValueError("Untranslated platform Jinja package path")
                for directory in ("third_party/jinja2", "third_party/markupsafe"):
                    root = physical(directory)
                    inputs.update("//" + directory + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.suffix == ".py")
            if "--template-dir" in args:
                directory = args[args.index("--template-dir") + 1]
                if directory != "../../third_party/dawn/generator/templates":
                    raise ValueError("Untranslated platform template path")
                root = physical(directory[6:])
                inputs.update("//" + directory[6:] + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.is_file())
            if "--expected-outputs-file" in args:
                extraction_label = label.removesuffix("__json_tarball")
                extraction = targets[extraction_label]
                if not label.endswith("__json_tarball") or extraction.get("script") != "//third_party/dawn/generator/extract_json.py" or extraction["args"][0] != args[args.index("--output-json-tarball") + 1]:
                    raise ValueError("Untranslated original Dawn output declaration")
                prefix = BUILD + extraction["args"][1] + "/"
                if any(not output.startswith(prefix) for output in extraction["outputs"]):
                    raise ValueError("Original Dawn output escapes generation root")
                path = BUILD + args[args.index("--expected-outputs-file") + 1]
                outputs = [output.removeprefix(prefix) for output in extraction["outputs"]]
                generated[path] = "\n".join(outputs) + "\n"
                literal_metadata[path] = dict(source="third_party/dawn/generator/generator_lib.gni", target=extraction_label, outputs=outputs)
                inputs.add(path)
            if target["script"] == "//mojo/public/tools/bindings/mojom_bindings_generator.py":
                template = {"c++": "cpp_templates.zip", "typescript": "ts_templates.zip", "javascript": "js_templates.zip"}[args[args.index("-g") + 1]]
                inputs.add(BUILD + args[args.index("--bytecode_path") + 1] + "/" + template)
            for arg in args:
                if arg.startswith("--") and "=" in arg:
                    arg = arg.split("=", 1)[1]
                if arg.startswith("../../") and physical(arg[6:]).is_file():
                    inputs.add("//" + arg[6:])
                elif BUILD + arg in graph["generated_files"]:
                    inputs.add(BUILD + arg)
            runs = []
            if kind == "action_foreach":
                for source in target["sources"]:
                    substitutions = {"{{source}}": "../../" + source[2:], "{{source_name_part}}": Path(source).stem, "{{source_gen_dir}}": "gen/" + posixpath.dirname(source[2:])}
                    expanded = args
                    for placeholder, value in substitutions.items():
                        expanded = [arg.replace(placeholder, value) for arg in expanded]
                    runs.append(dict(args=expanded, outputs=[BUILD + path for path in target["source_outputs"][source]]))
                if sorted(path for run in runs for path in run["outputs"]) != sorted(target["outputs"]):
                    raise ValueError("Platform foreach output expansion changed")
            else:
                runs.append(dict(args=args, outputs=target["outputs"]))
            if any("{{" in arg.replace("{{response_file_name}}", "") for run in runs for arg in run["args"]):
                raise ValueError("Untranslated platform generator placeholder")
            for path in sorted(inputs):
                input_file(path)
            record.update(script="third_party/node/node.py" if label == ELECTRON_GENERATORS["version_args"] else target["script"][2:], inputs=sorted(inputs - tools.keys()), tools={path: tools[path] for path in sorted(inputs) if path in tools}, outputs=target["outputs"], runs=runs, response=target.get("response_file_contents", []))
            record["environment"] = {"ANGLE_UPSTREAM_HASH": revisions["third_party/angle"]["commit"][:12]} if target["script"] == "//third_party/angle/src/commit_id.py" else {}
            if label in CONTENT_RESOURCES.values() or label == CONTENT_GENERATORS["model_descriptors"]:
                record["environment"]["PROTOBUF_PYTHON_IMPLEMENTATION"] = "python"
            if target["script"] in API_SCRIPTS:
                record["environment"]["ELECTRON_SOURCE_COPYRIGHT_YEAR"] = "2025"
            actions[label] = record
        elif kind == "copy":
            if len(target["sources"]) != len(target["outputs"]):
                raise ValueError("Unexpected original platform copy: " + label)
            for path in target["sources"]:
                input_file(path)
            record.update(sources=target["sources"], outputs=target["outputs"])
            copies[label] = record
        elif kind == "generated_file":
            for path in target["outputs"]:
                if path not in graph["generated_files"]:
                    raise ValueError("Missing captured literal platform metadata")
                input_file(path)
            record["outputs"] = target["outputs"]
            metadata[label] = record
        elif kind in ("group", "static_library", "source_set", "executable", "shared_library"):
            libraries[label] = capture_library(graph, target, record, input_file, label, SDK_LIBS | {"z"})
            if "third_party/ml_dtypes/src" in record["includes"]:
                # GN exposes these vendored headers through a config.
                if not ml_dtypes_headers:
                    root = physical("third_party/ml_dtypes/src")
                    ml_dtypes_headers = sorted("//third_party/ml_dtypes/src/" + path.relative_to(root).as_posix() for path in source_files(root) if path.suffix == ".h")
                    if not ml_dtypes_headers:
                        raise ValueError("Missing original ml_dtypes headers")
                for header in ml_dtypes_headers:
                    input_file(header)
                record["source_headers"] = sorted(set(record["source_headers"] + ml_dtypes_headers))
            if label in EXTRA_NATIVE_HEADERS:
                # These source-root includes are omitted from GN's file lists.
                extra_headers = set(EXTRA_NATIVE_HEADERS[label])
                pending_headers = [path for path in extra_headers if path.startswith("//third_party/cros_system_api/")]
                while pending_headers:
                    header = pending_headers.pop()
                    for included in source_includes(header[2:])[1]:
                        path = "//" + posixpath.normpath(posixpath.join(posixpath.dirname(header[2:]), included))
                        if not path.startswith("//third_party/cros_system_api/") or not physical(path[2:]).is_file():
                            raise ValueError("Missing relative system_api header: " + path)
                        if path not in extra_headers:
                            extra_headers.add(path)
                            pending_headers.append(path)
                for header in sorted(extra_headers):
                    input_file(header)
                record["source_headers"] = sorted(set(record["source_headers"]) | extra_headers)
            record["outputs"] = target.get("outputs", [])
            replaced_rust_flags = [flag for flag in record["gn_ldflags"] if flag.startswith("prebuilt_rustc_sysroot/lib/rustlib/x86_64-unknown-linux-gnu/lib/lib") and flag.endswith(".rlib")]
            if replaced_rust_flags:
                record["replaced_rust_toolchain_flags"] = replaced_rust_flags
            if label == "//third_party/wayland:wayland_scanner":
                record["native_configuration_headers"] = ["//third_party/wayland/include/config.h"]
            if label == "//components/url_formatter/spoof_checks/top_domains:top_domain_generator":
                record["native_tool_data"] = {"@electron_icu_sources//:common/icudtl.dat": "icudtl.dat"}
            linker_inputs = []
            for flag in record["gn_ldflags"]:
                if flag.startswith("-Wl,--version-script=../../"):
                    path = "//" + flag.removeprefix("-Wl,--version-script=../../")
                    input_file(path)
                    linker_inputs.append(path)
            record["linker_inputs"] = linker_inputs
        else:
            raise ValueError("Untranslated platform target kind: " + kind)
    input_file("//build/util/lastchange.py")
    actions[hook_label] = dict(
        name=hook_name, kind="action", gn_deps=[],
        script="build/util/lastchange.py", inputs=["//build/util/lastchange.py"], tools={},
        outputs=hook_outputs, runs=[dict(outputs=hook_outputs, args=["-m", "DAWN_COMMIT_HASH", "-s", "../../third_party/dawn", "--revision", "src/gpu/webgpu/DAWN_VERSION", "--header", "src/gpu/webgpu/dawn_commit_hash.h"])],
        response=[], environment={"BASE_COMMIT_HASH": dawn, "BASE_COMMIT_SUBMISSION_MS": "1759164973000"},
        checkout_hook={"source": "DEPS", "name": "lastchange_dawn", "command": original_command,
                       "commit_metadata": "https://github.com/google/dawn/commit/" + dawn},
    )
    actions[skia_hook_label] = dict(
        name=skia_hook_name, kind="action", gn_deps=[], scoped_checkout_hook=True,
        script="build/util/lastchange.py", inputs=["//build/util/lastchange.py"], tools={},
        outputs=skia_outputs, runs=[dict(outputs=skia_outputs, args=["-m", "SKIA_COMMIT_HASH", "-s", "../../third_party/skia", "--header", "src/skia/ext/skia_commit_hash.h"])],
        response=[], environment={"BASE_COMMIT_HASH": skia, "BASE_COMMIT_SUBMISSION_MS": "1759426246000"},
        checkout_hook={"source": "DEPS", "name": "lastchange_skia", "command": skia_command,
                       "commit_metadata": "https://github.com/google/skia/commit/" + skia},
    )
    for label, action in actions.items():
        ordering, visited, pending = set(), set(), list(action["gn_deps"])
        while pending:
            dependency = pending.pop()
            if dependency in visited or dependency not in seen:
                continue
            visited.add(dependency)
            if dependency in actions:
                ordering.add(dependency)
            elif targets[dependency]["type"] in ("group", "generated_file"):
                pending.extend(targets[dependency].get("deps", []))
        action["ordering_deps"] = sorted(ordering)
    for library in libraries.values():
        textual, visited = set(), set()
        pending = list(library["srcs"] + library["c_srcs"])
        while pending:
            source = pending.pop()
            if source.startswith(BUILD) or source in visited:
                continue
            visited.add(source)
            for include in source_includes(source[2:])[0]:
                candidates = [posixpath.normpath(posixpath.join(posixpath.dirname(source[2:]), include))]
                candidates += [posixpath.normpath(posixpath.join(directory, include)) for directory in library["includes"]]
                candidates += [include, posixpath.join("gen", include)]
                candidate = next((path for path in candidates if not path.startswith(("/", "../")) and (physical(path).is_file() or BUILD + path in producers or BUILD + path in graph["generated_files"])), None)
                if candidate is None:
                    raise ValueError("Missing original textual platform implementation: " + include)
                original = "//" + candidate if physical(candidate).is_file() else BUILD + candidate
                textual.add(original)
                input_file(original)
                pending.append(original)
        if textual:
            library["textual_headers"] = sorted(textual)
    # Quoted sibling includes must remain beside sources across profile boundaries.
    pending, visited = list(files), set()
    while pending:
        source = pending.pop()
        if source in visited or Path(source).suffix not in (".h", ".hh", ".hpp", ".inc", ".inl", ".def", ".cc", ".cpp", ".c", ".S", ".s"):
            continue
        visited.add(source)
        for include in source_includes(source)[1]:
            candidate = posixpath.normpath(posixpath.join(posixpath.dirname(source), include))
            if candidate.startswith(("/", "../")) or not physical(candidate).is_file():
                continue
            used_shared.discard("//" + candidate)
            if candidate not in files:
                files.add(candidate)
                pending.append(candidate)
    used_shared.discard("//tools/json_to_struct/json_to_struct.py")
    files.add("tools/json_to_struct/json_to_struct.py")
    for path in sorted(files):
        if not physical(path).is_file():
            raise ValueError("Missing original platform input: " + path)
    def native_actions(labels):
        selected, visited = set(), set()
        pending = [label for label in labels if label in libraries and libraries[label]["kind"] != "group"]
        while pending:
            label = pending.pop()
            if label in visited or label not in seen:
                continue
            visited.add(label)
            if label in actions and not actions[label].get("scoped_native_headers"):
                selected.add(label)
            pending.extend(targets[label].get("deps", []))
        selected.update(label for label in actions if label not in targets and not actions[label].get("scoped_checkout_hook"))
        return sorted(selected)

    native_header_actions = native_actions(libraries)
    platform_headers = list(dict.fromkeys(path for directory in platform_directories if directory != "third_party/wayland/include" for path in headers[directory]))
    platform_header_set = set(platform_headers)
    core_headers = list(dict.fromkeys(path for directory in core_directories if directory != "third_party/wayland/include" for path in headers[directory] if path not in platform_header_set))
    core_header_set = platform_header_set | set(core_headers)
    core_actions = native_actions(label for label in libraries if label in core_seen)
    module_headers = list(dict.fromkeys(path for directory in module_directories if directory != "third_party/wayland/include" for path in headers[directory] if path not in core_header_set))
    module_header_set = core_header_set | set(module_headers)
    module_actions = native_actions(label for label in libraries if label in module_seen)
    content_headers = list(dict.fromkeys(path for directory in content_directories if directory != "third_party/wayland/include" for path in headers[directory] if path not in module_header_set))
    content_headers = list(dict.fromkeys(content_headers + content_interfaces))
    content_header_set = module_header_set | set(content_headers)
    content_actions = native_actions(label for label in libraries if label in content_seen)
    header_layers = dict(
        platform=dict(headers=platform_headers, actions=native_actions(platform_seen)),
        blink_core=dict(
            libraries=sorted(label for label in libraries if label in core_seen and label not in platform_seen),
            headers=core_headers,
            actions=sorted(set(core_actions) - set(native_actions(platform_seen))),
        ),
        blink_modules=dict(
            libraries=sorted(label for label in libraries if label in module_seen and label not in core_seen),
            headers=module_headers,
            actions=sorted(set(module_actions) - set(core_actions)),
        ),
        content=dict(
            libraries=sorted(label for label in libraries if label in content_seen and label not in module_seen),
            headers=content_headers,
            actions=sorted(set(content_actions) - set(module_actions)),
        ),
        electron=dict(
            libraries=sorted(label for label in libraries if label not in content_seen),
            headers=list(dict.fromkeys(path for directory in directories if directory != "third_party/wayland/include" for path in headers[directory] if path not in content_header_set)),
            actions=sorted(set(native_header_actions) - set(content_actions)),
        ),
    )
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    devtools_actions = sorted(label for label in closure([DEVTOOLS_ROOT]) if label in actions)
    policy_script = "components/policy/resources/policy_templates.py"
    original = "f.write(' '.join(source_files))"
    if physical(policy_script).read_text().count(original) != 1:
        raise ValueError("Original policy depfile writer changed")
    source_adapters = {"//" + policy_script: {original: "f.write(' '.join(os.path.relpath(path) for path in source_files))"}}
    clock_adapters = {
        "feature_compiler.py": {"datetime.now().year": "int(os.environ['ELECTRON_SOURCE_COPYRIGHT_YEAR'])"},
        "cpp_util.py": {"datetime.now().year": "int(os.environ['ELECTRON_SOURCE_COPYRIGHT_YEAR'])"},
        "js_util.py": {"from datetime import datetime": "import os", "datetime.now().year": "int(os.environ['ELECTRON_SOURCE_COPYRIGHT_YEAR'])"},
        "ts_definition_generator.py": {"import datetime": "import os", "datetime.date.today().year": "int(os.environ['ELECTRON_SOURCE_COPYRIGHT_YEAR'])"},
    }
    for name, substitutions in clock_adapters.items():
        path = "tools/json_schema_compiler/" + name
        if any(physical(path).read_text().count(before) != 1 for before in substitutions):
            raise ValueError("Original schema compiler copyright source changed: " + path)
        source_adapters["//" + path] = substitutions
    return dict(electron_api_generators=api_generators, electron_repack_actions=sorted(label for label in actions if actions[label]["script"] == "tools/grit/pak_util.py"), electron_generators=ELECTRON_GENERATORS, content_generators=CONTENT_GENERATORS, source_adapters=source_adapters, content_web_assets=CONTENT_WEB_ASSETS, content_resources=CONTENT_RESOURCES, content_protobuf_runtime=CONTENT_PROTO_RUNTIME_COPIES, content_metadata=CONTENT_METADATA, devtools_workspace=devtools_workspace, devtools_frontend_actions=devtools_actions, header_layers=header_layers, devtools_esbuild=devtools_esbuild, copies=copies, devtools_node_modules_files=devtools_packages, native_header_actions=sorted(native_header_actions), source_aliases=source_aliases, roots=capture_roots, graph_sha256=digest, source_revisions=revisions, names=names, libraries=libraries, actions=actions, metadata=metadata, literal_metadata=literal_metadata, execution_tools=sorted(set(tools.values())), execution_closure=sorted(execution_closure), producers=producers, headers=headers, files=sorted(files), external_files={path: shared[path] for path in sorted(used_shared)}, external={label: external[label] for label in sorted(used)}, generated_files=generated, toolchain_deps=sorted(TOOLCHAIN), sdk_libraries=sorted(SDK_LIBS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-root", action="append", default=[])
    args = parser.parse_args()
    roots = dict(item.split("=", 1) for item in args.source_root)
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, {name: Path(path) for name, path in roots.items()}, args.profiles)
    args.output.write_text(json.dumps(pack_profile(profile), separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
