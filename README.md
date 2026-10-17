# Apple Cursor

Tiny Swift utility for classic-style arrow, hand and text-hover cursors on macOS 26–27. Requires Apple’s Command Line Tools.

```sh
sh build.sh
./.build/apple-cursor apply --size 24
./.build/apple-cursor reset
```

Sizes: 16–32 points; default 24. Runs once and exits. SIP stays enabled.

Artwork: [ful1e5/apple_cursor](https://github.com/ful1e5/apple_cursor). GPL-3.0. Uses private macOS APIs.
