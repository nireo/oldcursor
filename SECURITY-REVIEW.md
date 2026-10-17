# Local review — 2026-10-17

Review scope: the new Swift utility, C interface declarations, local build and
artwork conversion scripts, and pinned artwork. This was a source inspection and
automated validation, not an independent security audit or a proof of safety.

## Verified

- `main.swift`: 184 lines, plus 15 lines of C declarations. No downloaded code is
  compiled. Runtime cursor images are embedded PNG data, not executable plugins.
- Pinned upstream revision: `fe044a42b4e9cea16ea762d2ed9004f6d7b35543`.
  Downloaded archive SHA-256:
  `d3fd3e608fefb90c3cab1317397b054115b1a5495b68fb7886403f837928f329`.
  The per-file manifest records the selected original artwork and configuration.
- All 124 SVGs in the downloaded archive passed an initial check for scripts,
  entities, event handlers and external references. Only five selected SVGs are
  now vendored. The stricter regeneration validator also accepted these five files.
- The ten rendered PNG representations were decoded successfully and checked for
  exact 32/64-pixel dimensions, PNG type and 8-bit RGBA format. The preview was
  visually inspected for expected shapes and colors.
- Production build succeeded with Swift 6, optimization, warnings as errors and
  a macOS 26 deployment target, on this arm64 macOS 27 machine.
- `codesign --verify --strict` passed. The executable has hardened runtime enabled
  and no entitlement exceptions. `otool -L` showed only Apple system libraries.
- 68 automated command, malformed-artwork, sizing and registration/rollback checks passed.
  The test executable substitutes fake C functions for every private cursor API;
  its undefined symbols were checked to exclude real CGS/CoreCursor calls.
- `check` on the production binary validated five designs and 13 cursor identifiers
  without cursor changes. SIP status on this machine was `enabled`.
- The apply test checks the exact arrow/open-hand/closed-hand/pointing-hand/I-beam
  identifier set, clearing the previous theme before registering these 13
  identifiers, and aborting without registration if the initial reset fails.
- Sizing tests inspect the actual prepared CGImages and registration arguments at
  16, 20, 24 and 32 points, checking both 1x/2x pixel sizes and proportionally
  scaled hotspots for every registered cursor. Malformed and out-of-range size
  arguments fail before calling any private API. The default is now 24 points.

## Remaining limits

- The user reported that applying the previous 32-point version looked good.
  The agent has not run live `apply` or `reset`; the new sizing behavior has not
  yet been checked visually on the desktop. Automated cursor calls are mocked.
- Private Apple APIs have no public compatibility contract. C ABI declarations
  and correct behavior cannot be proven from a successful build or mock tests.
- `reset` is best effort for macOS cursor caches; it does not preserve another
  cursor tool's theme. Logging out and back in is the fallback recovery path.
- Native image decoders and operating-system code may contain vulnerabilities.
  Input bounds and using fixed artwork reduce exposure but cannot eliminate it.
- The executable is locally ad-hoc signed, not Developer ID signed or notarized.
  Do not treat the upstream hashes or this review as proof of authorship or the
  absence of malicious content.

No malicious executable content or obvious code-execution path was found in the
reviewed inputs. The program requires neither disabling SIP nor granting extra
privacy permissions. Future edits or rebuilt artwork require a fresh review.
