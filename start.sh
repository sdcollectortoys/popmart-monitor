#!/usr/bin/env bash
set -e

# ensure child Chrome processes are killed on exit
trap 'pkill -f chrome; pkill -f chromedriver' EXIT

# run the monitor
exec python3 monitor.py
