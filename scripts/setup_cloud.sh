#!/usr/bin/env bash
# Nội dung để dán vào ô "Setup script" của cloud environment (kết quả được cache).
# Không có secret nào ở đây.
set -euo pipefail
python3 -c 'import sys; assert sys.version_info >= (3, 12), "last30days cần Python >= 3.12"'
# yt-dlp: nguồn YouTube (tuỳ chọn — thiếu thì engine tự bỏ qua YouTube).
command -v yt-dlp >/dev/null 2>&1 || uv tool install yt-dlp || pip install --user --break-system-packages yt-dlp || true
