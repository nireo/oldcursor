#!/usr/bin/env python3
"""Offline SVG/PNG -> embedded PNG conversion. Needs Python 3.11+ and rsvg-convert.

No upstream scripts, package managers, network requests, or shell evaluation.
Ordinary builds use the committed Artwork.swift and do not need this tool.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tomllib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
# Themes map these roles to upstream images; macOS aliases stay shared.
MAPPING = {
    "arrow": (["Arrow", "ArrowS"], [0]),
    "closed_hand": (["ClosedHand"], [11]),
    "open_hand": (["OpenHand"], [12]),
    "pointing_hand": (["PointingHand"], [13]),
    "ibeam": (["IBeam", "IBeamS", "IBeamXOR"], [1]),
}

ALLOWED_TAGS = {
    "svg", "g", "path", "defs", "filter", "feFlood", "feColorMatrix",
    "feOffset", "feGaussianBlur", "feBlend", "clipPath", "rect",
    "feComposite", "linearGradient", "stop",
}


def passive_svg(data, colors):
    if len(data) > 262_144 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Oversized SVG or XML entities")
    root = ET.fromstring(data)
    box = [float(value) for value in root.get("viewBox", "").split()]
    if (root.tag != "{http://www.w3.org/2000/svg}svg" or len(box) != 4 or
            box[:2] != [0, 0] or
            any(not math.isfinite(value) or not 1 <= value <= 4096 for value in box[2:])):
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
            # Replace literal colors in one pass, without cascading substitutions.
            if key in {"fill", "stroke", "color", "stop-color", "flood-color", "lighting-color"} and value in colors:
                element.set(key, colors[value])
    root.set("preserveAspectRatio", "none")
    return ET.tostring(root), box[2], box[3]


def local_path(base, filename):
    path = (base / filename).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError(f"Path escapes source directory: {filename}")
    return path


def png_svg(data):
    # Only a bounded PNG is placed in this locally constructed SVG. Upstream
    # SVG resource references remain forbidden by passive_svg().
    if not 33 <= len(data) <= 98_304 or data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
        raise ValueError("Invalid or oversized source PNG")
    width, height, depth, color, compression, filtering, interlace = struct.unpack_from(">2I5B", data, 16)
    if (not 1 <= width <= 1024 or not 1 <= height <= 1024 or
            (depth, color, compression, filtering) != (8, 6, 0, 0) or interlace not in (0, 1)):
        raise ValueError("Expected a bounded 8-bit RGBA source PNG")
    encoded = base64.b64encode(data).decode("ascii")
    source = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
              f'viewBox="0 0 {width} {height}"><image width="{width}" height="{height}" '
              f'href="data:image/png;base64,{encoded}"/></svg>')
    return source.encode("ascii"), width, height


def xcursor_hotspot(data, width, height):
    # Read metadata only; no Xcursor decoder or upstream tooling is executed.
    if not 16 <= len(data) <= 131_072:
        raise ValueError("Invalid Xcursor metadata size")
    magic, header, version, count = struct.unpack_from("<4I", data)
    if (magic != 0x72756358 or header != 16 or version != 0x10000 or
            not 1 <= count <= 32 or header + count * 12 > len(data)):
        raise ValueError("Invalid Xcursor header")
    matches = []
    for index in range(count):
        kind, size, position = struct.unpack_from("<3I", data, header + index * 12)
        if kind != 0xFFFD0002 or size != width:
            continue
        if position < header + count * 12 or position + 36 > len(data):
            raise ValueError("Invalid Xcursor image offset")
        image_header, image_kind, image_size, image_version, w, h, x, y, _ = struct.unpack_from("<9I", data, position)
        if ((image_header, image_kind, image_size, image_version, w, h) !=
                (36, kind, size, 1, width, height) or x >= width or y >= height or
                position + image_header + width * height * 4 > len(data)):
            raise ValueError("Invalid Xcursor image metadata")
        matches.append((x, y))
    if len(matches) != 1:
        raise ValueError("Expected one static Xcursor image matching the source PNG")
    return matches[0]


def load_theme(path):
    theme = tomllib.loads(path.read_text())
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", theme["id"]):
        raise ValueError(f"Invalid theme ID: {path.name}")
    title = theme["title"]
    if not isinstance(title, str) or not title.strip() or not title.isprintable():
        raise ValueError(f"Invalid theme title: {path.name}")
    cursors = theme["cursors"]
    if not cursors or not cursors.keys() <= MAPPING.keys():
        raise ValueError(f"Unknown or empty cursor roles: {path.name}")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in cursors.values()):
        raise ValueError(f"Invalid cursor source name: {path.name}")
    colors = theme.get("colors", {})
    if any(not re.fullmatch(r"(?:#[0-9A-Fa-f]{6}|[A-Za-z]+)", source) or
           not re.fullmatch(r"#[0-9A-Fa-f]{6}", target) for source, target in colors.items()):
        raise ValueError(f"Invalid theme color: {path.name}")
    svg = "svg_directory" in theme and "config" in theme
    png = "png_directory" in theme and "xcursor_directory" in theme
    if (svg == png or (svg and ("png_directory" in theme or "xcursor_directory" in theme)) or
            (png and ("svg_directory" in theme or "config" in theme or colors))):
        raise ValueError(f"Use SVG/config or PNG/Xcursor sources; PNG themes cannot recolor: {path.name}")
    return theme


def generate(themes, converter):
    output = ["// Generated offline by regenerate-artwork.py; do not edit the base64 data.",
              "let embeddedThemes: [CursorTheme] = ["]
    total = 0
    cursor_count = 0
    for theme in themes:
        manifest_path = local_path(ROOT, theme["manifest"])
        source_root = manifest_path.parent
        manifest = json.loads(manifest_path.read_text())
        for filename, expected in manifest["files"].items():
            if hashlib.sha256(local_path(source_root, filename).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Upstream file changed: {filename}")

        def source_file(filename):
            if filename not in manifest["files"]:
                raise ValueError(f"Source file is not pinned in manifest: {filename}")
            return local_path(source_root, filename)

        if "config" in theme:
            config = tomllib.loads(source_file(theme["config"]).read_text())["cursors"]
            fallback = config["fallback_settings"]
        revision = manifest.get("commit") or manifest["version"]
        output.append(f"    // Source: {manifest['repository']} @ {revision}")
        output.append("    CursorTheme(id: " + json.dumps(theme["id"]) + ", title: " +
                      json.dumps(theme["title"], ensure_ascii=False) + ", artwork: [")
        for role, name in theme["cursors"].items():
            aliases, numeric = MAPPING[role]
            if "png_directory" in theme:
                source, width, height = png_svg(source_file(f"{theme['png_directory']}/{name}.png").read_bytes())
                x, y = xcursor_hotspot(source_file(f"{theme['xcursor_directory']}/{name}").read_bytes(), width, height)
            else:
                source, width, height = passive_svg(
                    source_file(f"{theme['svg_directory']}/{name}.svg").read_bytes(), theme.get("colors", {}))
                settings = config[name]
                x = settings.get("x_hotspot", fallback["x_hotspot"])
                y = settings.get("y_hotspot", fallback["y_hotspot"])
            x = x * 32 / width
            y = y * 32 / height
            if not all(math.isfinite(value) and 0 <= value < 32 for value in (x, y)):
                raise ValueError(f"Invalid hotspot: {theme['id']}/{name}")
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
            output.append("        EmbeddedCursor(name: " + json.dumps(name) + ", identifiers: " +
                          json.dumps(identifiers) + f", x: {x}, y: {y}, pngs: [")
            output.extend("            " + json.dumps(png) + "," for png in pngs)
            output.append("        ]),")
            cursor_count += 1
        output.append("    ]),")
    output.append("]\n")
    return "\n".join(output), cursor_count, total


def main():
    converter = shutil.which("rsvg-convert")
    if converter is None:
        raise SystemExit("rsvg-convert is required only for regenerating artwork")
    themes = [load_theme(path) for path in sorted((ROOT / "themes").glob("*.toml"))]
    ids = [theme["id"] for theme in themes]
    if not 1 <= len(themes) <= 32 or len(set(ids)) != len(ids) or "classic" not in ids:
        raise SystemExit("Expected 1–32 themes with unique IDs, including the default 'classic'")
    output, cursor_count, total = generate(themes, converter)
    (ROOT / "Artwork.swift").write_text(output)
    print(f"Embedded {len(themes)} themes, {cursor_count} static cursors, {total:,} PNG bytes.")


if __name__ == "__main__":
    main()
