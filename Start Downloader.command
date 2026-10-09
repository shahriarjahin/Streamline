#!/bin/sh
# macOS Finder launcher. The dashboard continues after this script exits.
cd "$(dirname "$0")" || exit 1
exec /bin/sh "./Start Downloader.sh"
