#!/usr/bin/env bash
set -eu

# Usage: ./validate.sh <path to emacs binary>

EMACS_BINARY="$(readlink -f "$1")"

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "${SCRIPT_DIR}"

export EMACSLOADPATH="${SCRIPT_DIR}/../../programs/emacs-29.4/lisp"

echo "Running script.el"
SCRIPT_OUTPUT=$("$EMACS_BINARY" -q --script script.el)

EXPECTED_OUTPUT="OUTPUT: 24"

if [[ $SCRIPT_OUTPUT == *"${EXPECTED_OUTPUT}"* ]]; then
    echo "Output was correct!"
else
    echo "Wrong output:"
    echo "${SCRIPT_OUTPUT}"
    echo "Expected:"
    echo "${EXPECTED_OUTPUT}"
    exit 1
fi
