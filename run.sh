#!/bin/bash
# Run any LegislAItive Report script using the project venv
# Usage: ./run.sh collector.py  or  ./run.sh analyst.py
cd "$(dirname "$0")"
exec ./venv/bin/python3 "src/$1" "${@:2}"
