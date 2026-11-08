# SPDX-License-Identifier: MIT
"""Check event inheritance across the original Blink Web IDL database."""

import json
from pathlib import Path
import sys


def require(condition, message):
    if not condition:
        raise SystemExit("check failed: blink_bindings " + message)


def read(path, suffix, export):
    document = json.loads(Path(path).read_text())
    require(document["metadata"] == {
        "namespace": "event_interface_names",
        "suffix": suffix,
        "export": export,
    }, "generated component metadata matches native export")
    entries = document["data"]
    names = [entry["name"] for entry in entries]
    require(names == sorted(set(names)), "event interfaces are unique and sorted")
    return {entry["name"]: entry for entry in entries}


def main():
    core = read(sys.argv[1], "", "CORE_EXPORT")
    modules = read(sys.argv[2], "Modules", "MODULES_EXPORT")
    require({"Event", "UIEvent", "MouseEvent", "KeyboardEvent"} <= core.keys(),
            "core includes direct and inherited event interfaces")
    require("RTCTrackEvent" in modules and "MouseEvent" not in modules and
            "RTCTrackEvent" not in core,
            "event interfaces retain component ownership")
    require("Window" not in core and "Document" not in core,
            "non event interfaces are excluded")
    require(core["MouseEvent"]["interfaceHeaderDir"].endswith("/core/events") and
            modules["RTCTrackEvent"]["interfaceHeaderDir"].endswith("/modules/peerconnection"),
            "generated events retain original native header directories")


if __name__ == "__main__":
    main()
