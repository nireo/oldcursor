#!/bin/sh
# Install or remove the current user's one-shot login agent. Never use sudo.
set -eu
cd -- "$(dirname -- "$0")"

usage() {
    echo "Usage: sh login.sh [--theme ID] [--size POINTS] | --remove" >&2
    exit 1
}

size=24
theme=classic
remove=false
if [ "$#" -eq 1 ] && [ "$1" = --remove ]; then
    remove=true
    shift
fi
seen_size=false
seen_theme=false
while [ "$#" -gt 0 ]; do
    [ "$#" -ge 2 ] || usage
    case "$1" in
        --size) [ "$seen_size" = false ] || usage; size=$2; seen_size=true ;;
        --theme) [ "$seen_theme" = false ] || usage; theme=$2; seen_theme=true ;;
        *) usage ;;
    esac
    shift 2
done
case "$size" in
    16|17|18|19|20|21|22|23|24|25|26|27|28|29|30|31|32) ;;
    *) echo "Size must be a whole number from 16 to 32 points." >&2; exit 1 ;;
esac
[ "$(id -u)" -ne 0 ] || { echo "Run as your desktop user, never with sudo." >&2; exit 1; }

label=local.tiny-apple-cursor
domain="gui/$(id -u)"
agent="$HOME/Library/LaunchAgents/$label.plist"
support="$HOME/Library/Application Support/Apple Cursor"
log="$HOME/Library/Logs/apple-cursor.log"

if [ "$remove" = true ]; then
    if launchctl print "$domain/$label" >/dev/null 2>&1; then
        launchctl bootout "$domain/$label"
    fi
    rm -f "$agent" "$support/apple-cursor"
    rmdir "$support" 2>/dev/null || true
    echo "Removed Apple Cursor login startup. Current cursors are unchanged."
    exit 0
fi

# Build and validate before replacing an existing installation.
launchctl print "$domain" >/dev/null
sh build.sh
./.build/apple-cursor check --theme "$theme" --size "$size"
temporary_plist=$(mktemp)
trap 'rm -f "$temporary_plist"' EXIT HUP INT TERM
plutil -create xml1 "$temporary_plist"
plutil -insert Label -string "$label" "$temporary_plist"
plutil -insert ProgramArguments -json '[]' "$temporary_plist"
plutil -insert ProgramArguments.0 -string "$support/apple-cursor" "$temporary_plist"
plutil -insert ProgramArguments.1 -string apply "$temporary_plist"
plutil -insert ProgramArguments.2 -string --size "$temporary_plist"
plutil -insert ProgramArguments.3 -string "$size" "$temporary_plist"
plutil -insert ProgramArguments.4 -string --theme "$temporary_plist"
plutil -insert ProgramArguments.5 -string "$theme" "$temporary_plist"
plutil -insert RunAtLoad -bool YES "$temporary_plist"
plutil -insert LimitLoadToSessionType -string Aqua "$temporary_plist"
plutil -insert StandardOutPath -string "$log" "$temporary_plist"
plutil -insert StandardErrorPath -string "$log" "$temporary_plist"
plutil -lint "$temporary_plist"

if launchctl print "$domain/$label" >/dev/null 2>&1; then
    launchctl bootout "$domain/$label"
fi
mkdir -p "$HOME/Library/LaunchAgents" "$support" "$HOME/Library/Logs"
install -m 755 .build/apple-cursor "$support/apple-cursor"
install -m 644 "$temporary_plist" "$agent"
launchctl enable "$domain/$label"
launchctl bootstrap "$domain" "$agent"
echo "Installed Apple Cursor theme $theme at $size points for this login and future logins."
echo "Log: $log"
