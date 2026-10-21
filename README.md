# Apple Cursor

Tiny Swift utility for classic-style arrow, hand and text-hover cursors on macOS 26–27. Requires Apple’s Command Line Tools.

```sh
sh build.sh
./.build/apple-cursor apply --size 24
./.build/apple-cursor reset
```

Sizes: 16–32 points; default 24. Runs once and exits. SIP stays enabled.

To apply automatically whenever you log in:

```sh
sh login.sh --size 24
```

This builds and installs a copy in `~/Library/Application Support/Apple Cursor`,
then loads a user LaunchAgent that applies the cursors now and once per graphical
login. No process stays running. Re-run the command to update the installed copy
or change its size. Output goes to `~/Library/Logs/apple-cursor.log`.

To remove login startup (leaving the current cursors as they are):

```sh
sh login.sh --remove
```

Artwork: [ful1e5/apple_cursor](https://github.com/ful1e5/apple_cursor). GPL-3.0. Uses private macOS APIs.
