#!/bin/bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
exec /usr/bin/gcc "$@"
