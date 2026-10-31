#!/usr/bin/env python3
"""Validate error paths with fake private APIs; never change the real cursor."""
import os
from pathlib import Path
import plistlib
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

MOCKS = r'''
#pragma once
#include <ApplicationServices/ApplicationServices.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int CGSConnectionID;
static inline int test_mode(const char *value) {
    const char *mode = getenv("TINY_TEST_API");
    return mode && strcmp(mode, value) == 0;
}
static inline CGSConnectionID CGSMainConnectionID(void) {
    fputs("API connection\n", stderr); return 37;
}
static inline CGError CGSRegisterCursorWithImages(CGSConnectionID c, char *name,
    bool global, bool instantly, CGSize size, CGPoint hotspot, NSUInteger frames,
    CGFloat duration, CFArrayRef images, int *seed) {
    static int calls = 0;
    fprintf(stderr, "API register %s\n", name);
    CGImageRef first = (CGImageRef)CFArrayGetValueAtIndex(images, 0);
    CGImageRef second = (CGImageRef)CFArrayGetValueAtIndex(images, 1);
    fprintf(stderr, "API geometry %.6f %.6f %.6f %.6f %zu %zu\n",
        size.width, size.height, hotspot.x, hotspot.y, CGImageGetWidth(first), CGImageGetWidth(second));
    CFDataRef pixels = CGDataProviderCopyData(CGImageGetDataProvider(first));
    const UInt8 *bytes = CFDataGetBytePtr(pixels);
    uint64_t hash = 14695981039346656037ULL;
    for (CFIndex i = 0; i < CFDataGetLength(pixels); ++i) hash = (hash ^ bytes[i]) * 1099511628211ULL;
    fprintf(stderr, "API pixels %llu\n", (unsigned long long)hash);
    CFRelease(pixels);
    if (++calls == 3 && (test_mode("fail-register") || test_mode("fail-reset"))) return kCGErrorFailure;
    return kCGErrorSuccess;
}
static inline CGError CGSSetRegisteredCursor(CGSConnectionID c, char *name, int *seed) {
    fputs("API activate\n", stderr); return kCGErrorSuccess;
}
static inline CGError CoreCursorUnregisterAll(CGSConnectionID c) {
    static int calls = 0;
    fputs("API unregister\n", stderr);
    ++calls;
    return (test_mode("fail-initial-reset") || (test_mode("fail-reset") && calls == 2))
        ? kCGErrorFailure : kCGErrorSuccess;
}
static inline CGError CoreCursorSet(CGSConnectionID c, int identifier) {
    fputs("API core\n", stderr); return kCGErrorSuccess;
}
static inline CGError CGSSetSystemDefinedCursor(CGSConnectionID c, int identifier) {
    fputs("API select\n", stderr); return kCGErrorSuccess;
}
static inline void CGSSetDockCursorOverride(CGSConnectionID c, bool enabled) {
    fprintf(stderr, "API dock %d\n", enabled);
}
static inline CGError CGSGetCursorScale(CGSConnectionID c, float *scale) {
    fputs("API get-scale\n", stderr); *scale = 1; return kCGErrorSuccess;
}
static inline CGError CGSSetCursorScale(CGSConnectionID c, float scale) {
    fprintf(stderr, "API scale %.2f\n", scale); return kCGErrorSuccess;
}
'''

MUTATIONS = '''
func mutate(_ artwork: [EmbeddedCursor]) -> [EmbeddedCursor] {
    let a = artwork[0]
    let mode = ProcessInfo.processInfo.environment["TINY_TEST_ART"] ?? ""
    switch mode {
    case "empty": return []
    case "too-many": return Array(repeating: a, count: 33)
    case "duplicate": return [a, a]
    case "arrow-only": return [a]
    default: break
    }
    var identifiers = a.identifiers
    var x = a.x
    var pngs = a.pngs
    switch mode {
    case "nan": x = .nan
    case "infinity": x = .infinity
    case "negative-hotspot": x = -1
    case "outside-hotspot": x = 32
    case "bad-id": identifiers = ["com.apple.bad\\0name"]
    case "slash-id": identifiers = ["com.apple.bad/name"]
    case "base64": pngs[0] = "invalid base64!"
    case "wrong-size": pngs[0] = pngs[1]
    case "oversized": pngs[0] = String(repeating: "A", count: 131_073)
    case "no-retina": pngs.removeLast()
    default: return artwork
    }
    return [EmbeddedCursor(name: a.name, identifiers: identifiers, x: x, y: a.y, pngs: pngs)]
}
let embeddedThemes: [CursorTheme] = originalThemes.map { theme in
    let target = ProcessInfo.processInfo.environment["TINY_TEST_THEME"] ?? "classic"
    return CursorTheme(id: theme.id, title: theme.title,
                       artwork: theme.id == target ? mutate(theme.artwork) : theme.artwork)
}
'''


def validate_login(temp, executable):
    # Exercise the real installer with an isolated destination and fake launchctl.
    # HOME is untouched, and no real launch agent can be loaded by this test.
    fixture = temp / "login"
    fixture.mkdir()
    script = (ROOT / "login.sh").read_text().replace("$HOME/Library/", f"{fixture}/Library/")
    (fixture / "login.sh").write_text(script)
    (fixture / "build.sh").write_text(
        "#!/bin/sh\nset -eu\nmkdir -p .build\ncp " + shlex.quote(str(executable)) +
        " .build/apple-cursor\n./.build/apple-cursor check --all-themes\n")
    mocks = fixture / "bin"
    mocks.mkdir()
    calls = fixture / "launchctl.log"
    launcher = mocks / "launchctl"
    launcher.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> " + shlex.quote(str(calls)) + "\n")
    launcher.chmod(0o755)
    env = os.environ | {"PATH": str(mocks) + os.pathsep + os.environ["PATH"],
                        "TINY_TEST_ART": "", "TINY_TEST_API": ""}
    agent = fixture / "Library/LaunchAgents/local.tiny-apple-cursor.plist"
    count = 0

    def run(arguments, expected=0):
        nonlocal count
        result = subprocess.run(["sh", str(fixture / "login.sh"), *arguments],
                                env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == expected, (arguments, result)
        count += 1
        return result

    for arguments, theme, size in (([], "classic", "24"), (["--size", "20"], "classic", "20"),
                                  (["--theme", "inverted", "--size", "32"], "inverted", "32"),
                                  (["--theme", "adwaita", "--size", "24"], "adwaita", "24"),
                                  (["--size", "16", "--theme", "classic"], "classic", "16")):
        run(arguments)
        plist = plistlib.loads(agent.read_bytes())
        assert plist["ProgramArguments"] == [str(fixture / "Library/Application Support/Apple Cursor/apple-cursor"),
                                              "apply", "--size", size, "--theme", theme]
        assert plist["RunAtLoad"] and plist["LimitLoadToSessionType"] == "Aqua"

    previous = agent.read_bytes()
    for arguments in (["--theme"], ["--theme", ""], ["--theme", "missing"],
                      ["--size", "33"], ["--theme", "classic", "--theme", "inverted"],
                      ["--size", "20", "--size", "24"], ["--remove", "--theme", "classic"]):
        before = calls.read_text()
        run(arguments, 1)
        assert agent.read_bytes() == previous
        changes = calls.read_text()[len(before):]
        assert not any(operation in changes for operation in ("bootout", "bootstrap", "enable")), changes
    run(["--remove"])
    assert not agent.exists()
    assert not (fixture / "Library/Application Support/Apple Cursor/apple-cursor").exists()
    return count


def main():
    with tempfile.TemporaryDirectory(prefix="tiny-apple-cursor-tests-") as directory:
        temp = Path(directory)
        source = (ROOT / "main.swift").read_text()
        app_start = "_ = NSApplication.shared.setActivationPolicy(.prohibited)"
        assert source.count(app_start) == 1
        # Skip AppKit's connection setup. All cursor calls are replaced by C mocks.
        (temp / "main.swift").write_text(source.replace(app_start, "// App startup omitted for mock tests."))
        (temp / "Mocks.h").write_text(MOCKS)
        artwork = (ROOT / "Artwork.swift").read_text().replace("let embeddedThemes:", "let originalThemes:")
        (temp / "Artwork.swift").write_text(artwork + MUTATIONS)
        executable = temp / "tests"
        subprocess.run(["xcrun", "swiftc", "-O", "-swift-version", "6", "-warnings-as-errors",
                        "-module-cache-path", str(ROOT / ".build/module-cache"),
                        "-import-objc-header", str(temp / "Mocks.h"), str(temp / "main.swift"),
                        str(temp / "Artwork.swift"), "-framework", "AppKit", "-framework",
                        "ApplicationServices", "-o", str(executable)], check=True)
        # Prove there are no unresolved real cursor mutation calls in this test binary.
        symbols = subprocess.run(["nm", "-u", str(executable)], capture_output=True, text=True, check=True).stdout
        assert not re.search(r"_(CGS|CoreCursor)", symbols), symbols

        count = 0

        def run(command, expected=0, art="", api="", art_theme="classic"):
            nonlocal count
            env = os.environ | {"TINY_TEST_ART": art, "TINY_TEST_API": api, "TINY_TEST_THEME": art_theme}
            result = subprocess.run([str(executable), *command], env=env, capture_output=True, text=True, timeout=15)
            assert result.returncode == expected, (command, art, api, result)
            count += 1
            return result

        for command in ([], ["--help"], ["check"], ["themes"], ["check", "--all-themes"]):
            assert "API " not in run(command).stderr
        listing = run(["themes"]).stdout
        assert listing.splitlines() == ["adwaita\tAdwaita", "classic\tClassic (default)", "inverted\tInverted"]
        for arguments in (["--all-themes"], ["--all-themes", "--size", "16"],
                          ["--size", "32", "--all-themes"]):
            result = run(["check", *arguments])
            assert "Validated classic:" in result.stdout and "Validated inverted:" in result.stdout
            assert "Validated adwaita:" in result.stdout
            assert "API " not in result.stderr
        for command in (["unknown"], ["apply", "extra"], ["reset", "extra"]):
            assert "API " not in run(command, 1).stderr
        for command in (["apply", "--size"], ["apply", "--unknown", "24"],
                        ["reset", "--size", "24"], ["apply", "--size", "24", "extra"],
                        ["themes", "--theme", "classic"], ["reset", "--theme", "classic"],
                        ["apply", "--all-themes"], ["check", "--all-themes", "--theme", "classic"],
                        ["check", "--all-themes", "--all-themes"],
                        ["apply", "--theme", "classic", "--theme", "inverted"],
                        ["check", "--size", "20", "--size", "24"], ["check", "--theme"]):
            assert "API " not in run(command, 1).stderr
        for theme in ("missing", "", "Classic", "../classic"):
            for command in ("check", "apply"):
                result = run([command, "--theme", theme], 1)
                assert "Unknown theme" in result.stderr and "API " not in result.stderr
        for size in ("nan", "inf", "0", "-1", "15", "33", "24.5", "huge", "", "9" * 100):
            for command in ("check", "apply"):
                assert "API " not in run([command, "--size", size], 1).stderr
        for mode in ("empty", "too-many", "duplicate", "nan", "infinity", "negative-hotspot",
                     "outside-hotspot", "bad-id", "slash-id", "base64", "wrong-size", "oversized", "no-retina"):
            for theme in ("classic", "inverted", "adwaita"):
                for command in ("check", "apply"):
                    result = run([command, "--theme", theme], 1, art=mode, art_theme=theme)
                    assert "API " not in result.stderr, (mode, result.stderr)
        assert "API " not in run(["check", "--all-themes"], 1, art="base64", art_theme="inverted").stderr
        assert "Validated classic:" in run(["check"], art="base64", art_theme="inverted").stdout
        assert "API " not in run(["check", "--all-themes"], 1, art="base64", art_theme="adwaita").stderr
        assert "Validated classic:" in run(["check"], art="base64", art_theme="adwaita").stdout

        applied = run(["apply"])
        expected_identifiers = {
            "com.apple.coregraphics.Arrow", "com.apple.coregraphics.ArrowS", "com.apple.cursor.0",
            "com.apple.coregraphics.ClosedHand", "com.apple.cursor.11",
            "com.apple.coregraphics.OpenHand", "com.apple.cursor.12",
            "com.apple.coregraphics.PointingHand", "com.apple.cursor.13",
            "com.apple.coregraphics.IBeam", "com.apple.coregraphics.IBeamS",
            "com.apple.coregraphics.IBeamXOR", "com.apple.cursor.1",
        }
        actual_identifiers = re.findall(r"^API register (.+)$", applied.stderr, re.M)
        assert set(actual_identifiers) == expected_identifiers and len(actual_identifiers) == 13
        assert applied.stderr.count("API activate") == 13
        assert applied.stderr.count("API unregister") == 1
        assert applied.stderr.index("API unregister") < applied.stderr.index("API register ")
        assert applied.stderr.count("API core") == 44
        assert applied.stderr.endswith("API scale 1.01\nAPI scale 1.00\n")
        assert applied.stderr == run(["apply", "--theme", "classic"]).stderr
        inverted = run(["apply", "--theme", "inverted"])
        assert inverted.stderr.count("API activate") == 13
        classic_pixels = re.findall(r"API pixels (\d+)", applied.stderr)
        inverted_pixels = re.findall(r"API pixels (\d+)", inverted.stderr)
        assert len(classic_pixels) == len(inverted_pixels) == 13
        assert all(a != b for a, b in zip(classic_pixels, inverted_pixels))
        assert inverted.stderr.index("API unregister") < inverted.stderr.index("API register ")
        assert inverted.stderr.count("API core") == 44
        for arguments in (["--size", "20", "--theme", "inverted"],
                          ["--theme", "inverted", "--size", "20"]):
            result = run(["apply", *arguments])
            assert "Applied inverted at 20 points" in result.stdout
            assert "API geometry 20.000000 20.000000" in result.stderr
        partial = run(["apply", "--theme", "inverted"], art="arrow-only", art_theme="inverted")
        assert partial.stderr.count("API register ") == 3
        assert partial.stderr.count("API core") == 44
        assert partial.stderr.index("API unregister") < partial.stderr.index("API register ")
        original = run(["apply", "--size", "32"])
        baseline = re.findall(r"API geometry ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) (\d+) (\d+)", original.stderr)
        assert len(baseline) == 13 and baseline[0] == ("32.000000", "32.000000", "10.000000", "4.750000", "32", "64")
        assert baseline[-1] == ("32.000000", "32.000000", "16.062257", "17.000000", "32", "64")
        # Hotspots from GNOME's 96px images, in the role order in adwaita.toml.
        adwaita_hotspots = [(12, 4)] * 3 + [(36, 20)] * 2 + [(44, 8)] * 2 + [(28, 20)] * 2 + [(44, 48)] * 4
        for size in (16, 20, 24, 32):
            checked = run(["check", "--theme", "adwaita", "--size", str(size)])
            assert "API " not in checked.stderr and "Validated adwaita:" in checked.stdout
            result = run(["apply", "--theme", "adwaita", "--size", str(size)])
            assert "Applied adwaita" in result.stdout
            ids = re.findall(r"^API register (.+)$", result.stderr, re.M)
            assert len(ids) == 13 and set(ids) == expected_identifiers
            assert result.stderr.index("API unregister") < result.stderr.index("API register ")
            assert result.stderr.count("API unregister") == 1 and result.stderr.count("API core") == 44
            geometries = re.findall(r"API geometry ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) (\d+) (\d+)", result.stderr)
            assert len(geometries) == len(adwaita_hotspots)
            for geometry, (source_x, source_y) in zip(geometries, adwaita_hotspots):
                width, height, x, y, pixels1, pixels2 = map(float, geometry)
                assert width == height == pixels1 == size and pixels2 == 2 * size
                assert abs(x - source_x * size / 96) < 0.000002
                assert abs(y - source_y * size / 96) < 0.000002
            if size == 24:
                adwaita_pixels = re.findall(r"API pixels (\d+)", result.stderr)
                assert len(adwaita_pixels) == 13
                assert all(a != b for a, b in zip(classic_pixels, adwaita_pixels))
                assert all(a != b for a, b in zip(inverted_pixels, adwaita_pixels))
        for size in (16, 20, 24, 32):
            checked = run(["check", "--size", str(size)])
            assert "API " not in checked.stderr and f"at {size} points" in checked.stdout
            result = applied if size == 24 else original if size == 32 else run(["apply", "--size", str(size)])
            geometries = re.findall(r"API geometry ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) (\d+) (\d+)", result.stderr)
            assert len(geometries) == 13
            for geometry, base in zip(geometries, baseline):
                width, height, x, y, pixels1, pixels2 = map(float, geometry)
                assert width == height == pixels1 == size and pixels2 == 2 * size
                assert abs(x - float(base[2]) * size / 32) < 0.000002
                assert abs(y - float(base[3]) * size / 32) < 0.000002
        reset = run(["reset"])
        assert reset.stderr.count("API unregister") == 1 and reset.stderr.count("API core") == 44
        assert "API dock 0" in reset.stderr and "API register" not in reset.stderr
        failed = run(["apply"], 1, api="fail-register")
        assert failed.stderr.count("API register ") == 3 and failed.stderr.count("API activate") == 2
        assert failed.stderr.count("API unregister") == 2 and "Register" in failed.stderr
        failed_reset = run(["apply"], 1, api="fail-reset")
        assert "Automatic reset also failed" in failed_reset.stderr and "Register" in failed_reset.stderr
        initial_reset = run(["apply"], 1, api="fail-initial-reset")
        assert "API register" not in initial_reset.stderr and "Unregister" in initial_reset.stderr
        failed = run(["apply", "--theme", "inverted"], 1, api="fail-register")
        assert failed.stderr.count("API unregister") == 2
        failed = run(["apply", "--theme", "adwaita"], 1, api="fail-register")
        assert failed.stderr.count("API unregister") == 2
        login_count = validate_login(temp, executable)
        print(f"Passed {count} command/validation/rollback checks and {login_count} login installer checks; "
              "all private APIs and launchctl were mocked.")


if __name__ == "__main__":
    main()
