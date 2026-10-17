#!/usr/bin/env python3
"""Offline, one-time SVG -> embedded PNG conversion. Needs Python 3.11+ and rsvg-convert.

No upstream scripts, package managers, network requests, or shell evaluation.
Ordinary builds use the committed Artwork.swift and do not need this tool.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
# Each row maps one upstream image to Apple's cursor names and numeric aliases.
MAPPING = [
    ("left_ptr", ["Arrow", "ArrowS"], [0]),
    ("move", ["ClosedHand"], [11]),
    ("hand1", ["OpenHand"], [12]),
    ("hand2", ["PointingHand"], [13]),
    ("xterm", ["IBeam", "IBeamS", "IBeamXOR"], [1]),
]

ALLOWED_TAGS = {
    "svg", "g", "path", "defs", "filter", "feFlood", "feColorMatrix",
    "feOffset", "feGaussianBlur", "feBlend", "clipPath", "rect",
    "feComposite", "linearGradient", "stop",
}


def passive_svg(data):
    if len(data) > 262_144 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Oversized SVG or XML entities")
    root = ET.fromstring(data)
    box = [float(value) for value in root.get("viewBox", "").split()]
    if (root.tag != "{http://www.w3.org/2000/svg}svg" or len(box) != 4 or
            box[:2] != [0, 0] or any(value not in (256, 257) for value in box[2:])):
        raise ValueError("Unexpected SVG canvas")
    for element in root.iter():
        if element.tag.split("}")[-1] not in ALLOWED_TAGS:
            raise ValueError("SVG contains an unexpected element")
        for key, value in element.attrib.items():
            if key.lower().startswith("on") or key.endswith("href"):
                raise ValueError("SVG event handler or resource reference")
            for target in re.findall(r"url\((.*?)\)", value):
                if not re.fullmatch(r"#[A-Za-z0-9_-]+", target):
                    raise ValueError("SVG external resource")
    root.set("preserveAspectRatio", "none")
    passive = ET.tostring(root).replace(b"#00FF00", b"#000000").replace(b"#0000FF", b"#FFFFFF")
    return passive, box[2], box[3]


def main():
    converter = shutil.which("rsvg-convert")
    if converter is None:
        raise SystemExit("rsvg-convert is required only for regenerating artwork")
    manifest = json.loads((ROOT / "upstream/manifest.json").read_text())
    for filename, expected in manifest["files"].items():
        if hashlib.sha256((ROOT / "upstream" / filename).read_bytes()).hexdigest() != expected:
            raise SystemExit(f"Upstream file changed: {filename}")
    config = tomllib.loads((ROOT / "upstream/configs/x.build.toml").read_text())["cursors"]
    fallback = config["fallback_settings"]
    output = ["// Generated offline by regenerate-artwork.py; do not edit the base64 data.",
              "// Source: ful1e5/apple_cursor @ " + manifest["commit"],
              "let embeddedArtwork: [EmbeddedCursor] = ["]
    total = 0
    for name, aliases, numeric in MAPPING:
        source, width, height = passive_svg((ROOT / "upstream/svg" / (name + ".svg")).read_bytes())
        settings = config[name]
        x = settings.get("x_hotspot", fallback["x_hotspot"]) * 32 / width
        y = settings.get("y_hotspot", fallback["y_hotspot"]) * 32 / height
        identifiers = ["com.apple.coregraphics." + alias for alias in aliases]
        identifiers += ["com.apple.cursor." + str(number) for number in numeric]
        pngs = []
        for size in (32, 64):
            image = subprocess.run([converter, "--width", str(size), "--height", str(size)],
                                   input=source, capture_output=True, check=True, timeout=10).stdout
            if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 98_304:
                raise ValueError("Unexpected renderer output")
            total += len(image)
            pngs.append(base64.b64encode(image).decode("ascii"))
        output.append("    EmbeddedCursor(name: " + json.dumps(name) + ", identifiers: " +
                      json.dumps(identifiers) + f", x: {x}, y: {y}, pngs: [")
        output.extend("        " + json.dumps(png) + "," for png in pngs)
        output.append("    ]),")
    output.append("]\n")
    (ROOT / "Artwork.swift").write_text("\n".join(output))
    print(f"Embedded {len(MAPPING)} static cursors, {total:,} PNG bytes.")


if __name__ == "__main__":
    main()
