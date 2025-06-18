# start.sh  (make sure this file is saved with Unix LF endings, no BOM)
#!/usr/bin/env bash
set -e
while true; do
  echo "▶️  Starting monitor.py at $(date)"
  python -u monitor.py
  echo "⚠️  monitor.py exited unexpectedly with code $? — restarting in 5 s" >&2
  sleep 5
done
