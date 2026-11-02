#!/usr/bin/env bash
# One-time VM setup. Blender comes from the official bpy wheel (download.blender.org is blocked in the cloud).
set -euo pipefail
if [ ! -x /opt/bpyenv/bin/python ]; then
	python3 -m venv /opt/bpyenv
	/opt/bpyenv/bin/pip install -q --upgrade pip
	/opt/bpyenv/bin/pip install -q bpy numpy pillow scipy
fi
/opt/bpyenv/bin/python -c "import bpy; print('bpy', bpy.app.version_string)"
