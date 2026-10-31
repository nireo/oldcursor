# Apple Cursor

Tiny Swift utility for bundled arrow, hand and text-hover cursor themes on macOS 26–27. Requires Apple’s Command Line Tools.

```sh
sh build.sh
./.build/apple-cursor themes
./.build/apple-cursor apply --size 24
./.build/apple-cursor apply --theme inverted --size 24
./.build/apple-cursor apply --theme adwaita --size 24
./.build/apple-cursor reset
```

Bundled themes: `classic` (the original artwork and default), `inverted`
(reverses the black and white artwork colors), and `adwaita` (GNOME's Adwaita
artwork from release 51.0). Classic has a black arrow and I-beam with white
outlines, and white hands with black outlines. All themes replace the arrow,
open and closed hands, pointing hand and text I-beam.
Switching themes restores macOS defaults for any cursors the new theme does not
include.

Sizes: 16–32 points; default 24. `--theme` and `--size` work in either order.
Runs once and exits. SIP stays enabled. Themes are embedded in the executable;
no artwork files are needed at runtime.

To validate images without changing your cursor:

```sh
./.build/apple-cursor check --theme inverted
./.build/apple-cursor check --theme adwaita
./.build/apple-cursor check --all-themes
```

`check` without a theme validates `classic`. Builds validate all bundled themes.

To apply automatically whenever you log in:

```sh
sh login.sh --size 24
# Or choose another theme:
sh login.sh --theme inverted --size 24
```

This builds and installs a copy in `~/Library/Application Support/Apple Cursor`,
then loads a user LaunchAgent that applies the cursors now and once per graphical
login. No process stays running. Re-run the command to update the installed copy
or change its theme or size. Omitting `--theme` selects `classic`. Output goes to
`~/Library/Logs/apple-cursor.log`.

To remove login startup (leaving the current cursors as they are):

```sh
sh login.sh --remove
```

To add a bundled theme, copy a definition in `themes/` and give it a unique `id`
and `title`. Its `manifest` path is relative to the repository root; `config`
and `svg_directory` are relative to that manifest's directory. The manifest pins
the source files by SHA-256 and records the upstream repository and commit or
release. Keep the source license alongside the artwork.

The `[colors]` table optionally maps literal SVG colors to replacements. The
`[cursors]` table maps supported roles (`arrow`, `closed_hand`, `open_hand`,
`pointing_hand`, `ibeam`) to SVG basenames. Omitted roles use macOS defaults.
Hotspots come from the source config (the same TOML format as
`upstream/configs/x.build.toml`), normalized to the 32-point canvas. SVG viewBoxes
must start at `0 0`, with width and height from 1 to 4096. Every SVG and the config
must be listed in the source manifest.

PNG themes such as Adwaita use `png_directory` and `xcursor_directory` instead of
`svg_directory` and `config`. The PNGs must be 8-bit RGBA; a matching static
Xcursor image supplies each hotspot. Both files must be pinned in the manifest.
The generator reads only Xcursor metadata and resizes the PNGs to 32/64 pixels
using `rsvg-convert`. Color replacement applies only to SVG themes. The same
embedded-image validation runs for every theme before any cursor changes.

Regenerate and rebuild after editing definitions (Python 3.11+ and
`rsvg-convert` are needed only for regeneration):

```sh
python3 regenerate-artwork.py
sh build.sh
python3 tests/artwork.py
python3 tests/validate.py
```

The validation suite uses mocked private APIs and an isolated login installer
with mocked `launchctl`; it does not apply cursors or change login startup.

Original artwork: [ful1e5/apple_cursor](https://github.com/ful1e5/apple_cursor),
GPL-3.0. Adwaita artwork: [GNOME Project](https://www.gnome.org/); source,
attribution and license notices are in [upstream/adwaita](upstream/adwaita/README.md).
Uses private macOS APIs.
