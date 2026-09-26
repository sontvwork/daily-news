#!/usr/bin/env python3
"""Tiện ích cho pipeline Daily News (chỉ dùng stdlib).

  news.py validate    DATE   kiểm tra news/DATE.md đúng format bản tin
  news.py site        DATE   build index.html + feed.xml + briefs/ bằng `library feed`, kiểm tra link local
  news.py link        DATE   in đường dẫn tương đối của trang bài DATE (lấy từ feed.xml)
  news.py summary     DATE   in đúng 3 dòng tóm tắt (.cache/work/summary.txt, fallback: 3 tiêu đề đầu)
  news.py verify-live DATE   poll GitHub Pages tới khi index, feed và mọi trang bài trả 200
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "news"
ENGINE = ROOT / ".claude/skills/last30days/scripts/last30days.py"
SUMMARY_FILE = ROOT / ".cache/work/summary.txt"
ATOM = "{http://www.w3.org/2005/Atom}"
DAILY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
ITEM_HEADING = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
NO_NEWS_PHRASE = "Không có tin mới nổi bật"


def fail(message: str) -> None:
    print(f"news.py: {message}", file=sys.stderr)
    sys.exit(1)


def title_for(date: str) -> str:
    y, m, d = date.split("-")
    return f"Daily News {d}/{m}/{y}"


def daily_path(date: str) -> Path:
    return NEWS / f"{date}.md"


def cmd_validate(date: str) -> None:
    path = daily_path(date)
    if not path.is_file():
        fail(f"không thấy {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > 200_000:
        fail("bản tin quá lớn (>200KB)")
    lines = text.splitlines()
    first = next((line for line in lines if line.strip()), "")
    if first.strip() != f"# {title_for(date)}":
        fail(f"dòng đầu phải là '# {title_for(date)}', đang là {first!r}")
    if sum(1 for line in lines if re.match(r"^#\s", line)) != 1:
        fail("chỉ được có đúng một heading cấp 1 (title)")
    items = ITEM_HEADING.findall(text)
    if not items:
        if NO_NEWS_PHRASE not in text:
            fail(f"không có tin '### 1. ...' nào và cũng không có câu '{NO_NEWS_PHRASE}'")
        print(f"OK: {path.name} — ngày không có tin mới")
        return
    numbers = [int(n) for n, _ in items]
    if numbers != list(range(1, len(numbers) + 1)):
        fail(f"số thứ tự tin phải liên tục từ 1, đang là {numbers}")
    # Mỗi tin cần ít nhất một bullet trước heading kế tiếp.
    for block in re.split(r"^###\s+\d+\.", text, flags=re.MULTILINE)[1:]:
        if not re.search(r"^\s*[-*]\s+\S", block, re.MULTILINE):
            fail("mỗi tin phải có ít nhất một bullet")
    print(f"OK: {path.name} — {len(items)} tin")


def normalize_mtimes() -> None:
    """Checkout làm reset mtime; parser library dùng mtime làm ngày cho file tên YYYY-MM-DD.md."""
    for path in NEWS.glob("*.md"):
        match = DAILY_FILE.match(path.name)
        if not match:
            continue
        noon = datetime.fromisoformat(match.group(1)).replace(hour=12, tzinfo=timezone.utc).timestamp()
        os.utime(path, (noon, noon))


def feed_entries() -> list[tuple[str, str]]:
    """[(published YYYY-MM-DD, href)] từ news/feed.xml."""
    feed = NEWS / "feed.xml"
    if not feed.is_file():
        fail("chưa có news/feed.xml — chạy `news.py site` trước")
    root = ET.parse(feed).getroot()
    entries = []
    for entry in root.findall(f"{ATOM}entry"):
        published = (entry.findtext(f"{ATOM}published") or "")[:10]
        link = entry.find(f"{ATOM}link")
        entries.append((published, link.get("href", "") if link is not None else ""))
    return entries


def cmd_site(date: str) -> None:
    normalize_mtimes()
    env = dict(os.environ, SETUP_COMPLETE="true", LAST30DAYS_LIBRARY_OWNER="Daily News")
    proc = subprocess.run(
        [sys.executable, str(ENGINE), "library", "feed", f"--save-dir={NEWS}"],
        env=env, capture_output=True, text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        fail(f"library feed exit {proc.returncode}")
    if "Library note: Skipped" in proc.stderr:
        fail("library feed bỏ qua một số file .md (xem log ở trên)")
    if list(NEWS.rglob("*.bak*")):
        fail("library feed tạo file .bak — có trang không do nó sinh ra trong news/")

    entries = feed_entries()
    missing = [href for _, href in entries if not (NEWS / href).is_file()]
    index_links = set(re.findall(r'href="(briefs/[^"]+\.html)"', (NEWS / "index.html").read_text(encoding="utf-8")))
    missing += [href for href in index_links if not (NEWS / href).is_file()]
    if missing:
        fail(f"link hỏng: {sorted(set(missing))}")
    if not any(published == date for published, _ in entries):
        fail(f"feed.xml không có bài ngày {date}")
    print(f"OK: {len(entries)} bài trong feed, {len(index_links)} link trong index, không link hỏng")


def cmd_link(date: str) -> None:
    hrefs = [href for published, href in feed_entries() if published == date]
    if len(hrefs) != 1:
        fail(f"cần đúng 1 bài ngày {date} trong feed.xml, thấy {len(hrefs)}")
    print(hrefs[0])


def cmd_summary(date: str) -> None:
    if SUMMARY_FILE.is_file():
        lines = [line.strip() for line in SUMMARY_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(lines) == 3:
            for line in lines:
                print(re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", line)[:220])
            return
        print(f"news.py: summary.txt có {len(lines)} dòng (cần 3) — dùng fallback", file=sys.stderr)
    text = daily_path(date).read_text(encoding="utf-8")
    titles = [title for _, title in ITEM_HEADING.findall(text)][:3]
    if not titles:
        titles = [f"😴 {NO_NEWS_PHRASE} trong 24 giờ qua."]
    fillers = [
        "🔎 Nguồn: Reddit, Hacker News, X, YouTube, GitHub, web (last30days).",
        "📚 Xem chi tiết và các số trước qua link bên dưới.",
    ]
    titles += fillers[len(titles) - 1:][: 3 - len(titles)]
    for title in titles:
        print(title[:220])


def http_ok(url: str) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "daily-news-verify"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def cmd_verify_live(date: str, base: str, timeout: int) -> None:
    base = base.rstrip("/")
    today = next(href for published, href in feed_entries() if published == date)
    paths = ["index.html", "feed.xml"] + [href for _, href in feed_entries()]
    deadline = time.monotonic() + timeout
    # Chờ bản deploy mới (trang bài hôm nay lên) rồi mới kiểm tra toàn bộ.
    while not http_ok(f"{base}/{today}?v={int(time.time())}"):
        if time.monotonic() > deadline:
            fail(f"quá {timeout}s mà {base}/{today} chưa trả 200")
        time.sleep(15)
    broken = [p for p in paths if not http_ok(f"{base}/{p}?v={int(time.time())}")]
    if broken:
        fail(f"trang live lỗi: {broken}")
    print(f"OK: {len(paths)} URL live trả 200 — {base}/{today}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["validate", "site", "link", "summary", "verify-live"])
    parser.add_argument("date")
    parser.add_argument("--base", default=os.environ.get("PAGES_BASE_URL", ""))
    parser.add_argument("--timeout", type=int, default=420)
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        fail("DATE phải dạng YYYY-MM-DD")
    if args.command == "validate":
        cmd_validate(args.date)
    elif args.command == "site":
        cmd_site(args.date)
    elif args.command == "link":
        cmd_link(args.date)
    elif args.command == "summary":
        cmd_summary(args.date)
    else:
        if not args.base:
            fail("thiếu --base hoặc PAGES_BASE_URL")
        cmd_verify_live(args.date, args.base, args.timeout)


if __name__ == "__main__":
    main()
