#!/usr/bin/env python3
"""Validate offline artwork import bounds and provenance without cursor APIs."""
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("artwork_generator", ROOT / "regenerate-artwork.py")
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)
SOURCE = ROOT / "upstream/adwaita"


class ArtworkTests(unittest.TestCase):
    def test_release_hotspots(self):
        for name, expected in {"default": (12, 4), "grabbing": (36, 20), "grab": (44, 8),
                               "pointer": (28, 20), "text": (44, 48)}.items():
            with self.subTest(cursor=name):
                data = (SOURCE / "src/cursors/pngs/96x96" / f"{name}.png").read_bytes()
                svg, width, height = generator.png_svg(data)
                self.assertEqual((width, height), (96, 96))
                image = list(ET.fromstring(svg))[0]
                self.assertTrue(image.get("href").startswith("data:image/png;base64,"))
                cursor = (SOURCE / "Adwaita/cursors" / name).read_bytes()
                self.assertEqual(generator.xcursor_hotspot(cursor, width, height), expected)

    def test_reject_invalid_png(self):
        original = (SOURCE / "src/cursors/pngs/96x96/default.png").read_bytes()
        for label, offset, value, fmt in (("magic", 0, 0, "B"), ("width", 16, 1025, ">I"),
                                          ("height", 20, 0, ">I"), ("depth", 24, 16, "B"),
                                          ("color", 25, 2, "B"), ("compression", 26, 1, "B")):
            with self.subTest(field=label):
                data = bytearray(original)
                struct.pack_into(fmt, data, offset, value)
                with self.assertRaises(ValueError):
                    generator.png_svg(data)
        for data in (original[:16], original + b"\0" * 98_304):
            with self.assertRaises(ValueError):
                generator.png_svg(data)

    def test_reject_invalid_xcursor(self):
        original = (SOURCE / "Adwaita/cursors/default").read_bytes()
        # The final TOC entry is the 96px image used for the PNG source.
        toc = 16 + 5 * 12
        position = struct.unpack_from("<I", original, toc + 8)[0]
        for label, offset, value in (("magic", 0, 0), ("header", 4, 100), ("count", 12, 33),
                                     ("offset", toc + 8, 0xFFFFFFFF),
                                     ("inside-toc", toc + 8, 16),
                                     ("image-header", position, 35), ("width", position + 16, 95),
                                     ("height", position + 20, 95), ("hotspot", position + 24, 96)):
            with self.subTest(field=label):
                data = bytearray(original)
                struct.pack_into("<I", data, offset, value)
                with self.assertRaises(ValueError):
                    generator.xcursor_hotspot(data, 96, 96)
        for data in (original[:15], original[:-1], original + b"\0" * 131_072):
            with self.assertRaises(ValueError):
                generator.xcursor_hotspot(data, 96, 96)
        with self.assertRaisesRegex(ValueError, "one static"):
            generator.xcursor_hotspot(original, 32, 32)
        duplicate = bytearray(original)
        duplicate[16:28] = original[toc:toc + 12]
        with self.assertRaisesRegex(ValueError, "one static"):
            generator.xcursor_hotspot(duplicate, 96, 96)

    def test_reject_changed_or_unpinned_source_before_rendering(self):
        theme = generator.load_theme(ROOT / "themes/adwaita.toml")
        with tempfile.TemporaryDirectory(prefix="adwaita-provenance-") as directory:
            fixture = Path(directory)
            source = fixture / "upstream/adwaita"
            shutil.copytree(SOURCE, source)
            png = source / "src/cursors/pngs/96x96/default.png"
            original = png.read_bytes()
            png.write_bytes(original + b"\0")
            with patch.object(generator, "ROOT", fixture), patch.object(generator.subprocess, "run") as render:
                with self.assertRaisesRegex(ValueError, "Upstream file changed"):
                    generator.generate([theme], "unused-renderer")
                render.assert_not_called()
            png.write_bytes(original)
            manifest = source / "manifest.json"
            metadata = json.loads(manifest.read_text())
            del metadata["files"]["src/cursors/pngs/96x96/default.png"]
            manifest.write_text(json.dumps(metadata))
            with patch.object(generator, "ROOT", fixture), patch.object(generator.subprocess, "run") as render:
                with self.assertRaisesRegex(ValueError, "not pinned"):
                    generator.generate([theme], "unused-renderer")
                render.assert_not_called()

    def test_reject_svg_resource_references(self):
        for content in ('<image href="https://example.com/image.png"/>',
                        '<path fill="url(https://example.com/paint)"/>', '<script/>'):
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">{content}</svg>'
            with self.subTest(content=content), self.assertRaises(ValueError):
                generator.passive_svg(svg.encode(), {})

    def test_reject_mixed_source_formats(self):
        original = (ROOT / "themes/adwaita.toml").read_text()
        for line in ('config = "config.toml"', 'svg_directory = "svg"'):
            with tempfile.TemporaryDirectory(prefix="adwaita-definition-") as directory:
                theme = Path(directory) / "theme.toml"
                theme.write_text(line + "\n" + original)
                with self.assertRaisesRegex(ValueError, "Use SVG/config or PNG/Xcursor"):
                    generator.load_theme(theme)


if __name__ == "__main__":
    unittest.main()
