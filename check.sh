#!/usr/bin/env bash
set -Eeuo pipefail

rye fmt --check
rye run mypy --strict .
rye lint
rye test
