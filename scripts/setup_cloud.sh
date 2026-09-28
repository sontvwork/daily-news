#!/usr/bin/env bash
# Nội dung để dán vào ô "Setup script" của cloud environment (kết quả được cache).
# Không có secret nào ở đây.
set -euo pipefail
# last30days cần Python >= 3.12. Image cloud có python3 = 3.11 nhưng cài sẵn python3.12/3.13;
# research.sh và news.py tự chọn bản đủ mới, ở đây chỉ kiểm tra là có ít nhất một bản.
found=""
for py in python3 python3.12 python3.13 python3.14; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
    found="$py"; break
  fi
done
[[ -n "$found" ]] || { echo "last30days cần Python >= 3.12 (python3.12 trở lên)" >&2; exit 1; }
# yt-dlp: nguồn YouTube (tuỳ chọn — thiếu thì engine tự bỏ qua YouTube).
command -v yt-dlp >/dev/null 2>&1 || uv tool install yt-dlp || pip install --user --break-system-packages yt-dlp || true
