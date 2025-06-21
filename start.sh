#!/usr/bin/env bash
set -e

trap 'pkill -f chrome; pkill -f chromedriver' EXIT
exec python3 monitor.py
