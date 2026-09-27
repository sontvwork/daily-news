#!/usr/bin/env python3
"""Tiện ích cho pipeline Daily News (chỉ dùng stdlib).

  news.py validate    DATE   kiểm tra news/DATE.md đúng format bản tin
  news.py prune       DATE   xoá .md/raw/briefs có ngày < DATE − (RETENTION_DAYS − 1)
  news.py site        DATE   feed.xml bằng `library feed` + trang card dashboard (theme/), kiểm tra link local
  news.py link        DATE   in đường dẫn tương đối của trang bài DATE (lấy từ feed.xml)
  news.py summary     DATE   in 1–3 dòng tóm tắt, y hệt card trang chủ (news/raw/DATE-summary.txt, fallback: tiêu đề tin)
  news.py verify-live DATE   poll GitHub Pages tới khi index, feed và mọi trang bài trả 200
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from site_render import parse_issue, read_summary, render_site, summary_lines, summary_path

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "news"
THEME = ROOT / "theme"
CONFIG = ROOT / "config/news.env"
ENGINE = ROOT / ".claude/skills/last30days/scripts/last30days.py"
LIBRARY_ID = ".last30days-library-id"
ATOM = "{http://www.w3.org/2005/Atom}"
DAILY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
# File có ngày của bản tin — chỉ những file này mới bị prune xoá (guard.sh giữ bản regex riêng, khớp với đây).
DATED_FILES = [
    (NEWS, DAILY_FILE),
    (NEWS / "raw", re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9-]+\.(?:md|json|txt)$")),
    (NEWS / "briefs", re.compile(r"^[a-z0-9-]+-[0-9a-f]{8}-(\d{4}-\d{2}-\d{2})\.html$")),
]
ITEM_HEADING = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
NO_NEWS_PHRASE = "Không có tin mới nổi bật"
SUMMARY_MAX_CHARS = 100
# Markdown bị cấm trong tóm tắt: bold/italic/code/strike, link, _nghiêng_.
SUMMARY_MARKDOWN = re.compile(r"[*`]|~~|\]\(|(?<!\w)_\S[^_]*_(?!\w)")


def fail(message: str) -> None:
    print(f"news.py: {message}", file=sys.stderr)
    sys.exit(1)


def title_for(date: str) -> str:
    y, m, d = date.split("-")
    return f"Daily News {d}/{m}/{y}"


def daily_path(date: str) -> Path:
    return NEWS / f"{date}.md"


def config_value(key: str) -> str:
    """Giá trị `KEY=value` / `KEY="value"` trong config/news.env (không chạy bash)."""
    match = re.search(rf'^{key}=(?:"([^"]*)"|(\S*))', CONFIG.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        fail(f"config/news.env thiếu {key}")
    return match.group(1) if match.group(1) is not None else match.group(2)


def retention_days() -> int:
    value = config_value("RETENTION_DAYS")
    if not re.fullmatch(r"[1-9]\d*", value):
        fail(f"RETENTION_DAYS phải là số nguyên ≥ 1, đang là {value!r}")
    return int(value)


def site_base_path() -> str:
    """Đường dẫn gốc của site trên Pages (vd /daily-news/) — trang 404 được phục vụ ở mọi độ sâu."""
    return urlsplit(config_value("PAGES_BASE_URL")).path.rstrip("/") + "/"


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
        check_summary(date)
        print(f"OK: {path.name} — ngày không có tin mới")
        return
    numbers = [int(n) for n, _ in items]
    if numbers != list(range(1, len(numbers) + 1)):
        fail(f"số thứ tự tin phải liên tục từ 1, đang là {numbers}")
    # Mỗi tin cần ít nhất một bullet trước heading kế tiếp.
    for block in re.split(r"^###\s+\d+\.", text, flags=re.MULTILINE)[1:]:
        if not re.search(r"^\s*[-*]\s+\S", block, re.MULTILINE):
            fail("mỗi tin phải có ít nhất một bullet")
    check_summary(date)
    print(f"OK: {path.name} — {len(items)} tin")


def check_summary(date: str) -> None:
    """news/raw/DATE-summary.txt: 1–3 dòng plain text, mỗi dòng = 1 emoji + câu ngắn. Thiếu file chỉ cảnh báo."""
    path = summary_path(NEWS, Date.fromisoformat(date))
    name = path.relative_to(ROOT)
    if not path.is_file():
        print(f"news.py: cảnh báo — thiếu {name}, trang chủ và Google Chat sẽ dùng tiêu đề tin", file=sys.stderr)
        return
    lines = read_summary(NEWS, Date.fromisoformat(date))
    if lines is None:
        fail(f"{name} phải có 1–3 dòng không rỗng")
    for line in lines:
        head, _, rest = line.partition(" ")
        if unicodedata.category(head[0]) != "So" or any(ch.isalnum() for ch in head) or not rest.strip():
            fail(f"{name}: mỗi dòng phải mở đầu bằng 1 emoji + dấu cách: {line[:60]!r}")
        if any(unicodedata.category(ch) == "So" for ch in rest):
            fail(f"{name}: mỗi dòng chỉ được 1 emoji (ở đầu dòng): {line[:60]!r}")
        if SUMMARY_MARKDOWN.search(line):
            fail(f"{name}: không dùng markdown (bold/italic/code/link): {line[:60]!r}")
        if len(line) > SUMMARY_MAX_CHARS:
            fail(f"{name}: dòng dài {len(line)} > {SUMMARY_MAX_CHARS} ký tự: {line[:60]!r}")


def cmd_prune(date: str) -> None:
    """Xoá file có ngày < DATE − (RETENTION_DAYS − 1). Mốc chỉ phụ thuộc DATE nên chạy lại không xoá thêm."""
    if not daily_path(date).is_file():
        fail(f"không thấy {daily_path(date).relative_to(ROOT)} — chỉ prune theo bản tin đã có")
    keep = retention_days()
    cutoff = Date.fromisoformat(date) - timedelta(days=keep - 1)
    removed = []
    for folder, pattern in DATED_FILES:
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            match = pattern.match(path.name)
            if not match or path.is_symlink() or not path.is_file():
                continue
            try:
                day = Date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if day < cutoff:
                path.unlink()
                removed.append(path.relative_to(ROOT).as_posix())
    for path in removed:
        print(f"  xoá {path}")
    print(f"OK: giữ {keep} ngày (từ {cutoff.isoformat()}), xoá {len(removed)} file quá hạn")


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


def build_feed() -> None:
    """Chạy `library feed` trên bản sao news/*.md trong thư mục tạm; chỉ lấy feed.xml về news/.

    HTML của engine bị bỏ — trang do site_render dựng, cùng tên file với link trong feed.
    """
    with tempfile.TemporaryDirectory(prefix="daily-news-library-") as tmp:
        library = Path(tmp)
        for path in NEWS.glob("*.md"):
            if DAILY_FILE.match(path.name):
                shutil.copy2(path, library / path.name)  # giữ mtime đã chuẩn hoá
        if (NEWS / LIBRARY_ID).is_file():
            shutil.copy2(NEWS / LIBRARY_ID, library / LIBRARY_ID)  # feed id ổn định
        env = dict(os.environ, SETUP_COMPLETE="true", LAST30DAYS_LIBRARY_OWNER="Daily News")
        proc = subprocess.run(
            [sys.executable, str(ENGINE), "library", "feed", f"--save-dir={library}"],
            env=env, capture_output=True, text=True,
        )
        sys.stderr.write(proc.stderr.replace(str(library.resolve()), "<tmp>").replace(str(library), "<tmp>"))
        if proc.returncode != 0:
            fail(f"library feed exit {proc.returncode}")
        if "Library note: Skipped" in proc.stderr:
            fail("library feed bỏ qua một số file .md (xem log ở trên)")
        shutil.copyfile(library / "feed.xml", NEWS / "feed.xml")
        if not (NEWS / LIBRARY_ID).is_file():
            shutil.copy2(library / LIBRARY_ID, NEWS / LIBRARY_ID)


def cmd_site(date: str) -> None:
    normalize_mtimes()
    build_feed()
    entries = feed_entries()
    pages = {Date.fromisoformat(published): href for published, href in entries}
    dailies = {DAILY_FILE.match(p.name).group(1) for p in NEWS.glob("*.md") if DAILY_FILE.match(p.name)}
    if len(pages) != len(entries) or {d.isoformat() for d in pages} != dailies:
        fail(f"feed.xml không khớp 1-1 với news/YYYY-MM-DD.md ({len(entries)} entry, {len(dailies)} file)")
    render_site(NEWS, THEME, pages, retention_days=retention_days(), base_path=site_base_path())

    missing = [href for _, href in entries if not (NEWS / href).is_file()]
    index_html = (NEWS / "index.html").read_text(encoding="utf-8")
    local_links = set(re.findall(r'href="((?:briefs|assets)/[^"#]+)"', index_html))
    missing += [href for href in local_links if not (NEWS / href).is_file()]
    missing += [page for page in ("assets/style.css", "404.html") if not (NEWS / page).is_file()]
    if missing:
        fail(f"link hỏng: {sorted(set(missing))}")
    if date not in dailies:
        fail(f"feed.xml không có bài ngày {date}")
    print(f"OK: {len(entries)} bài trong feed, {len(local_links)} link local trong index, không link hỏng")


def cmd_link(date: str) -> None:
    hrefs = [href for published, href in feed_entries() if published == date]
    if len(hrefs) != 1:
        fail(f"cần đúng 1 bài ngày {date} trong feed.xml, thấy {len(hrefs)}")
    print(hrefs[0])


def cmd_summary(date: str) -> None:
    """In 1–3 dòng tóm tắt — đúng những dòng trên card trang chủ (site_render.summary_lines)."""
    issue = parse_issue(daily_path(date), Date.fromisoformat(date), "")
    if issue.summary is None:
        print("news.py: không có tóm tắt hợp lệ — dùng tiêu đề tin", file=sys.stderr)
    for line in summary_lines(issue):
        print(line)


def fetch(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": "daily-news-verify"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read() if response.status == 200 else None
    except (urllib.error.URLError, TimeoutError):
        return None


def cmd_verify_live(date: str, base: str, timeout: int) -> None:
    """Chờ tới khi mọi file của site trên Pages giống hệt bản vừa build (tức bản deploy mới đã lên)."""
    base = base.rstrip("/")
    paths = ["index.html", "404.html", "feed.xml", "assets/style.css"] + [href for _, href in feed_entries()]
    deadline = time.monotonic() + timeout
    while True:
        pending = [p for p in paths if fetch(f"{base}/{p}?v={int(time.time())}") != (NEWS / p).read_bytes()]
        if not pending:
            break
        if time.monotonic() > deadline:
            fail(f"quá {timeout}s mà Pages vẫn chưa khớp bản build: {pending}")
        time.sleep(15)
    today = next(href for published, href in feed_entries() if published == date)
    print(f"OK: {len(paths)} URL live trả 200 và khớp bản build — {base}/{today}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["validate", "prune", "site", "link", "summary", "verify-live"])
    parser.add_argument("date")
    parser.add_argument("--base", default=os.environ.get("PAGES_BASE_URL", ""))
    parser.add_argument("--timeout", type=int, default=420)
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        fail("DATE phải dạng YYYY-MM-DD")
    if args.command == "validate":
        cmd_validate(args.date)
    elif args.command == "prune":
        cmd_prune(args.date)
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
