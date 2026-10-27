#!/bin/sh
set -eu

ryujin_root=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
ryujin_uv=$(command -v uv || true)

if [ -z "$ryujin_uv" ]; then
    for ryujin_candidate in \
        "${HOME:-}/.local/bin/uv" \
        "${HOME:-}/.cargo/bin/uv" \
        /opt/homebrew/bin/uv \
        /usr/local/bin/uv
    do
        if [ -x "$ryujin_candidate" ]; then
            ryujin_uv=$ryujin_candidate
            break
        fi
    done
fi

if [ -z "$ryujin_uv" ]; then
    echo "Ryujin requires uv. Install it or add it to the agent's PATH." >&2
    exit 1
fi

ryujin_script=${1:?Expected a Python tool filename}
shift
exec "$ryujin_uv" run --project "$ryujin_root/tools" --locked \
    "$ryujin_root/tools/$ryujin_script" "$@"
