#!/usr/bin/env bash
set -eu

# Usage: ./validate.sh <path to embench binary>

# The embench binaries already include validation code, and have exit code 1 on failure
echo "Running $1"
if $1; then
    echo "$1 exited successfully!"
else
    echo "$1 failed!"
    exit 1
fi
