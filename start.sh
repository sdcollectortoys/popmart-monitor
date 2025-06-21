#!/usr/bin/env bash
set -e

# Ensure any stray Chrome/Chromedriver processes are killed on exit
trap 'pkill -f chrome; pkill -f chromedriver' EXIT

# Launch the monitor
exec python3 monitor.py
