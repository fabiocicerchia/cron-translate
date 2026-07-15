#!/usr/bin/env bash
set -euo pipefail
# One-line installer for cron-translate
# Usage: curl -fsSL https://raw.githubusercontent.com/fabiocicerchia/cron-translate/main/install.sh | bash

if command -v pipx &>/dev/null; then
  pipx install git+https://github.com/fabiocicerchia/cron-translate
else
  pip install --user git+https://github.com/fabiocicerchia/cron-translate
fi
echo "cron-translate installed. Run: cron-translate --help"
