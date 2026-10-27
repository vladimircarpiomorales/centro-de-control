#!/usr/bin/env bash
# Arranca MeTube en puerto 8086 (background)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.local/bin:$PATH"  # deno para resolver los retos JS de YouTube (yt-dlp-ejs)
cd "$SCRIPT_DIR/metube"
PORT=8086 YTDL_OPTIONS='{"cookiesfrombrowser": ["firefox"]}' nohup "$SCRIPT_DIR/metube/venv/bin/python" "$SCRIPT_DIR/metube/app/main.py" >> "$SCRIPT_DIR/metube.log" 2>&1 &
echo "MeTube iniciado (PID $!)"
