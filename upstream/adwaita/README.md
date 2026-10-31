# Adwaita artwork

Artwork by the [GNOME Project](https://www.gnome.org/), from the official
[adwaita-icon-theme 51.0 release](https://download.gnome.org/sources/adwaita-icon-theme/51/).

Only five static shapes are included: `default` (arrow), `grabbing` (closed
hand), `grab` (open hand), `pointer` (pointing hand), and `text` (I-beam).

The files under `src/cursors/pngs/96x96/` and `Adwaita/cursors/` are unmodified
release files. The latter contain the matching image sizes and hotspots. The
local generator reads their metadata and resizes the 96px PNGs into the 32px
and 64px images embedded in `Artwork.swift`. These resized images are the only
artwork adaptation. No upstream scripts, installers, or build tools are run,
and no source images or Xcursor files are loaded by the app at runtime.

The archive was verified against GNOME's published
[SHA-256 checksum](https://download.gnome.org/sources/adwaita-icon-theme/51/adwaita-icon-theme-51.0.sha256sum):

```text
ba561cf3c96305a47179fa5605856ad695c9238ea07f7093aebd9ba80c4e323b  adwaita-icon-theme-51.0.tar.xz
```

`manifest.json` records the archive URL, checksum, release and per-file SHA-256
hashes. All 14 imported files were copied individually as regular files from
the verified archive. Regeneration is offline and rejects changed or unpinned
inputs.

The original `COPYING`, `COPYING_CCBYSA3`, `COPYING_LGPL` and `AUTHORS` files
are preserved here. Upstream offers the artwork under LGPL v3 or Creative
Commons Attribution-ShareAlike 3.0; see those notices for the terms. Attribution:
"GNOME Project", https://www.gnome.org/.
