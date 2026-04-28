#!/bin/bash
# Wrapper to force ARM-native Chrome on Apple Silicon
# DrissionPage's x64 Chrome via Rosetta breaks DevTools WebSocket
exec arch -arm64 "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "$@"
