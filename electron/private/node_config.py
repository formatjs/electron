# SPDX-License-Identifier: MIT
"""Translate captured target settings with Node's real config.gypi generator."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("script", "settings", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    settings = json.loads(args.settings.read_text(encoding="utf-8"))
    if hashlib.sha256(args.script.read_bytes()).hexdigest() != settings["generator_sha256"]:
        raise ValueError("Node config generator differs from captured target settings")
    sys.path.insert(0, str(args.script.parent.resolve()))
    spec = importlib.util.spec_from_file_location("electron_node_config", args.script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Upstream uses sys.platform for the suffix; this is target configuration.
    module.sys = SimpleNamespace(platform=settings["target_os"])
    config = settings["gn_config"]
    config["napi_build_version"] = module.getnapibuildversion.get_napi_version()
    with tempfile.TemporaryDirectory(prefix="electron-node-config-") as temporary:
        (Path(temporary) / "v8_features.json").write_text(json.dumps(settings["v8_features"]), encoding="utf-8")
        features = module.get_v8_config(temporary, "//third_party/electron_node")
        result = module.translate_config(temporary, config, features)
    args.output.write_text(repr(result), encoding="utf-8")


if __name__ == "__main__":
    main()
