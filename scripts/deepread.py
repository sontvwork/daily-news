#!/usr/bin/env python3
"""Deep-read tin dự kiến đăng: bài gốc + comment top của đúng thread Hacker News (chỉ dùng stdlib).

  deepread.py DATE URL...   đọc từng URL, gộp vào news/raw/DATE/deep.json, in 1 dòng tình trạng mỗi URL
  deepread.py probe URL...  debug môi trường: in proxy (đã che credential), DNS, kết quả đọc từng URL; KHÔNG ghi file

URL là URL gốc (blog, repo GitHub) hoặc link Hacker News (news.ycombinator.com/item?id=N → đọc cả bài
mà story trỏ tới). Thread Hacker News của URL gốc lấy từ metadata.hn_url trong news/raw/DATE/*-nominations.json,
nên comment luôn thuộc đúng story đã đề cử (khác top_comment của leg 2, vốn gom từ mọi kết quả tìm theo keyword).
Mạng trên cloud (kiểm tra 24/10/2026): github.com bị proxy chặn → README đọc qua raw.githubusercontent.com;
Reddit chặn IP datacenter → bỏ qua. URL lỗi không làm script fail: tin đó chỉ còn dữ kiện của bundle.

An toàn: deep.json được commit vào repo public, còn URL đến từ dữ liệu bên thứ ba → chỉ đọc http(s) tới địa chỉ
công khai (kiểm cả từng bước redirect). Cả lượt chạy có hạn DEADLINE_SECONDS; file được ghi sau mỗi URL xong.

Debug (môi trường cloud có proxy/sandbox khác local): mỗi lỗi ghi lý do đầy đủ (vd body của 403 do proxy trả về),
comment HN lỗi được đếm (`comments_failed`), và `runs[]` ghi môi trường + tổng kết từng lượt chạy. Lượt chạy
không có dòng trong `runs[]` = bị kill giữa chừng (vd Bash timeout).
"""

from __future__ import annotations

import html
import http.client
import ipaddress
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "news"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HN_LINK = re.compile(r"^https?://news\.ycombinator\.com/item\?id=(\d+)")
GITHUB_REPO = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?(?:[?#].*)?$")
GITHUB_BLOB = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)/blob/(.+)$")
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
LOCAL_SUFFIXES = (".localhost", ".local", ".internal")
# Không đọc được bằng HTTP thuần: chặn IP datacenter (Reddit) hoặc nội dung render bằng JS.
SKIP_HOSTS = ("reddit.com", "redd.it", "x.com", "twitter.com", "youtube.com", "youtu.be",
              "tiktok.com", "instagram.com", "polymarket.com")
USER_AGENT = "Mozilla/5.0 (compatible; daily-news-deepread)"
TIMEOUT = 15  # mỗi thao tác socket, không phải cả request → cần thêm DEADLINE_SECONDS
DEADLINE_SECONDS = 120
MAX_BYTES = 2_000_000
ARTICLE_MAX_CHARS = 4000
COMMENT_MAX_CHARS = 500
TOP_COMMENTS = 5
MAX_KIDS_SCANNED = 10  # comment bị xoá/dead không tính, nên quét dư vài cái
MIN_ARTICLE_CHARS = 500  # <article>/<main> ngắn hơn thì lấy cả <body>
REASON_MAX_CHARS = 200
USERINFO = re.compile(r"(?<=://)[^/\s@]+@")  # user:pass@ trong URL proxy, phòng lỗi in ra credential
DNS_VIA_PROXY = []  # host không resolve được DNS, phải để proxy tự resolve (chỉ để debug môi trường)
DNS_LOCK = threading.Lock()


class FetchError(Exception):
    pass


def describe(exc: BaseException, detail: str = "") -> str:
    """Lý do lỗi đủ để debug từ xa: tên lỗi + chi tiết (URLError.reason, body của HTTP lỗi), đã che credential."""
    if isinstance(exc, urllib.error.HTTPError):
        text = f"HTTP {exc.code} {exc.reason}"
    elif isinstance(exc, urllib.error.URLError):
        text = f"URLError: {exc.reason}"
    else:
        text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    if detail:
        text += f" — {re.sub(r'<[^>]+>', ' ', detail)}"  # body lỗi thường là trang HTML
    return clip(USERINFO.sub("***@", " ".join(text.split())), REASON_MAX_CHARS)


def check_url(url: str) -> None:
    """Chỉ cho http(s) tới địa chỉ công khai: chặn file://, localhost, mạng nội bộ, metadata cloud (169.254.169.254)."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        raise FetchError("URL không hợp lệ") from None
    if parts.scheme not in ("http", "https") or not host:
        raise FetchError("chỉ đọc URL http(s)")
    if host == "localhost" or host.endswith(LOCAL_SUFFIXES):
        raise FetchError(f"host nội bộ ({host})")
    try:
        addresses = [info[4][0] for info in socket.getaddrinfo(host, None)]
    except (OSError, UnicodeError) as exc:
        if urllib.request.getproxies():  # sandbox chỉ ra mạng qua proxy: proxy tự resolve, chỉ kiểm được IP viết thẳng
            addresses = [host]
            with DNS_LOCK:
                DNS_VIA_PROXY.append(host)
        else:
            raise FetchError(f"DNS lỗi ({describe(exc)})") from None
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            continue  # tên miền (nhánh proxy)
        if not ip.is_global:
            raise FetchError(f"địa chỉ không công khai ({ip})")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)  # trang công khai có thể redirect vào mạng nội bộ
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SafeRedirect)


def fetch(url: str) -> tuple[str, str]:
    """(nội dung đã decode, content type). URL không an toàn, lỗi mạng/HTTP → FetchError với lý do ngắn."""
    check_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with OPENER.open(request, timeout=TIMEOUT) as response:
            body = response.read(MAX_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            return body.decode(charset, errors="replace"), response.headers.get_content_type()
    except urllib.error.HTTPError as exc:  # body của 403/5xx cho biết ai chặn (proxy sandbox hay site)
        try:
            body = exc.read(500).decode("utf-8", errors="replace")
        except (OSError, http.client.HTTPException):
            body = ""
        raise FetchError(describe(exc, body)) from None
    except (OSError, http.client.HTTPException, LookupError) as exc:  # URLError, timeout ⊂ OSError
        raise FetchError(describe(exc)) from None


def tidy(text: str) -> str:
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


class TextExtractor(HTMLParser):
    """Text của trang HTML, ưu tiên <article> rồi <main>; bỏ script/style/nav/footer…

    Không bỏ <header>: có site (Webflow) đặt cả thân bài trong <header class="section_blog-post_body">.
    """

    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "aside", "form",
            "button", "iframe", "template"}
    BLOCK = {"p", "div", "li", "br", "tr", "pre", "blockquote", "section", "article", "main",
             "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "dd", "dt", "figcaption"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skipping = 0
        self.depth = {"article": 0, "main": 0}
        self.parts: dict[str, list[str]] = {"article": [], "main": [], "body": []}
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.depth:
            self.depth[tag] += 1
        self.in_title = tag == "title"
        if tag in self.BLOCK:
            self.add("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1
        elif tag in self.depth and self.depth[tag]:
            self.depth[tag] -= 1
        if tag == "title":
            self.in_title = False
        if tag in self.BLOCK:
            self.add("\n")

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        elif not self.skipping:
            self.add(data)

    def add(self, text: str) -> None:
        self.parts["body"].append(text)
        for key, depth in self.depth.items():
            if depth:
                self.parts[key].append(text)

    def text(self) -> str:
        for key in ("article", "main"):
            text = tidy("".join(self.parts[key]))
            if len(text) >= MIN_ARTICLE_CHARS:
                return text
        return tidy("".join(self.parts["body"]))


def markdown_text(text: str) -> str:
    """README markdown → text: bỏ comment/tag HTML và ảnh, giữ nguyên phần còn lại."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    return tidy(re.sub(r"<[^>]+>", "", text))


def hn_html(text: str) -> str:
    """Text comment/story của Hacker News API là HTML (<p>, <a>, <i>, <pre>)."""
    return tidy(html.unescape(re.sub(r"<[^>]+>", "", text.replace("<p>", "\n"))))


def read_article(url: str) -> dict:
    host = (urlsplit(url).hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in SKIP_HOSTS):
        return {"url": url, "status": "skipped", "reason": f"{host} không đọc được bằng HTTP thuần"}
    fetch_url, kind = url, "html"
    if match := GITHUB_REPO.match(url):
        fetch_url, kind = f"https://raw.githubusercontent.com/{match[1]}/{match[2]}/HEAD/README.md", "markdown"
    elif match := GITHUB_BLOB.match(url):
        fetch_url, kind = f"https://raw.githubusercontent.com/{match[1]}/{match[2]}/{match[3]}", "markdown"
    try:
        body, content_type = fetch(fetch_url)
    except FetchError as exc:
        return {"url": url, "status": "error", "reason": str(exc)}
    title = ""
    if kind == "markdown" or content_type in ("text/markdown", "text/plain"):
        text = markdown_text(body)
    elif content_type in ("text/html", "application/xhtml+xml"):
        parser = TextExtractor()
        parser.feed(body)
        text, title = parser.text(), tidy(parser.title)
    else:
        return {"url": url, "status": "skipped", "reason": f"content type {content_type}"}
    if not text:
        return {"url": url, "status": "error", "reason": "trang không có text (có thể render bằng JS)"}
    return {"url": url, "status": "ok", "title": title, "chars": len(text), "text": clip(text, ARTICLE_MAX_CHARS)}


def hn_item(item_id: str | int) -> dict:
    body, _ = fetch(HN_ITEM.format(item_id))
    item = json.loads(body)
    if not isinstance(item, dict):
        raise FetchError(f"không có item {item_id}")
    return item


def hn_comment(item_id: int) -> dict | str | None:
    """Comment đã rút gọn; None nếu bị xoá/dead; str = lý do lỗi khi tải."""
    try:
        comment = hn_item(item_id)
    except (FetchError, ValueError) as exc:
        return str(exc) or describe(exc)
    if comment.get("deleted") or comment.get("dead") or not comment.get("text"):
        return None
    return {"author": comment.get("by", ""), "replies": len(comment.get("kids", [])),
            "text": clip(hn_html(comment["text"]), COMMENT_MAX_CHARS)}


def top_comments(story: dict) -> tuple[list[dict], list[str]]:
    """(tối đa TOP_COMMENTS comment cấp đầu theo rank của Hacker News, lý do lỗi của các comment tải hỏng).

    `kids` đã xếp sẵn theo rank. Tải song song.
    """
    kids = story.get("kids", [])[:MAX_KIDS_SCANNED]
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(hn_comment, kids))
    comments = [result for result in results if isinstance(result, dict)]
    return comments[:TOP_COMMENTS], [result for result in results if isinstance(result, str)]


def read_one(url: str, hn_ids: dict[str, str]) -> dict:
    entry: dict = {"url": url}
    article_url = url
    match = HN_LINK.match(url)
    story_id = match[1] if match else hn_ids.get(url_key(url))
    if story_id:
        entry["hn_url"] = f"https://news.ycombinator.com/item?id={story_id}"
        try:
            story = hn_item(story_id)
        except (FetchError, ValueError) as exc:
            entry["hn_error"] = str(exc) or describe(exc)
        else:
            entry["hn"] = {"title": story.get("title", ""), "points": story.get("score"),
                           "comments": story.get("descendants")}
            entry["comments"], failed = top_comments(story)
            if failed:
                entry["comments_failed"] = len(failed)
                entry["comments_error"] = failed[0]
            if match:
                article_url = story.get("url") or ""
            if story.get("text"):  # Ask/Show HN: phần mô tả của người đăng
                entry["hn"]["text"] = clip(hn_html(story["text"]), ARTICLE_MAX_CHARS)
    if article_url and not HN_LINK.match(article_url):
        entry["article"] = read_article(article_url)
    return entry


def url_key(url: str) -> str:
    """Khoá so khớp URL: bỏ scheme, www., utm_*, fragment và '/' cuối."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url
    host = (parts.hostname or "").removeprefix("www.")
    query = "&".join(p for p in parts.query.split("&") if p and not p.startswith("utm_"))
    return host + parts.path.rstrip("/") + (f"?{query}" if query else "")


def nominated_hn_ids(date: str) -> dict[str, str]:
    """URL gốc (khoá url_key) → id story Hacker News, từ bundle leg 1 của mọi domain."""
    ids = {}
    for path in sorted((NEWS / "raw" / date).glob("*-nominations.json")):
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for nomination in bundle.get("nominations", []):
            for item in (nomination.get("nomination") or {}).get("items", []):
                match = HN_LINK.match((item.get("metadata") or {}).get("hn_url") or "")
                if match and item.get("url"):
                    ids.setdefault(url_key(item["url"]), match[1])
    return ids


def status_line(entry: dict) -> str:
    if "error" in entry:
        return f"- {entry['url']}: lỗi ({entry['error']})"
    parts = []
    article = entry.get("article")
    if article:
        detail = f"{article['chars']} ký tự" if article["status"] == "ok" else article["reason"]
        parts.append(f"bài gốc {article['status']} ({detail})")
    if "hn_url" in entry:
        parts.append(f"HN lỗi ({entry['hn_error']})" if "hn_error" in entry
                     else f"{len(entry.get('comments', []))} comment HN")
    if entry.get("comments_failed"):
        parts.append(f"{entry['comments_failed']} comment tải lỗi ({entry['comments_error']})")
    return f"- {entry['url']}: {', '.join(parts) or 'không có gì để đọc'}"


def run_summary(entries: list[dict], started: datetime, seconds: float) -> dict:
    """Môi trường + tổng kết một lượt chạy, để nhận ra lỗi hệ thống (proxy chặn, DNS hỏng…) qua nhiều ngày."""
    articles = [entry["article"] for entry in entries if "article" in entry]
    threads = [entry for entry in entries if "hn_url" in entry]
    reasons: dict[str, int] = {}
    for reason in ([a["reason"] for a in articles if a["status"] == "error"]
                   + [e["hn_error"] for e in threads if "hn_error" in e]
                   + [e["comments_error"] for e in entries if "comments_error" in e]
                   + [e["error"] for e in entries if "error" in e]):
        reasons[reason] = reasons.get(reason, 0) + 1
    counts = {
        "urls": len(entries),
        "articles_ok": sum(a["status"] == "ok" for a in articles),
        "articles_error": sum(a["status"] == "error" for a in articles),
        "articles_skipped": sum(a["status"] == "skipped" for a in articles),
        "hn_ok": sum("hn_error" not in e for e in threads),
        "hn_error": sum("hn_error" in e for e in threads),
        "comments_failed": sum(e.get("comments_failed", 0) for e in entries),
        "url_errors": sum("error" in e for e in entries),
    }
    summary = (f"{counts['articles_ok']}/{len(articles)} bài gốc ok ({counts['articles_skipped']} bỏ qua), "
               f"{counts['hn_ok']}/{len(threads)} thread HN ok, {counts['comments_failed']} comment lỗi, "
               f"{counts['url_errors']} URL quá hạn/lỗi script, {seconds:.1f}s")
    return {
        "started_at": started.isoformat(timespec="seconds"),
        "seconds": round(seconds, 1),
        "python": sys.version.split()[0],
        "proxy": bool(urllib.request.getproxies()),  # chỉ ghi có/không: URL proxy có thể chứa credential
        "dns_via_proxy": sorted(set(DNS_VIA_PROXY)),
        **counts,
        "top_errors": dict(sorted(reasons.items(), key=lambda kv: -kv[1])[:5]),
        "summary": summary,
    }


def probe(urls: list[str]) -> None:
    """Không ghi file: chạy được trong session routine trên cloud mà không để lại thay đổi trong news/."""
    proxies = {key: USERINFO.sub("***@", value) for key, value in urllib.request.getproxies().items()}
    print(json.dumps({"python": sys.version.split()[0], "proxies": proxies}, ensure_ascii=False))
    for host in ("hacker-news.firebaseio.com", "raw.githubusercontent.com", "github.com", "example.com"):
        try:
            addresses = sorted({info[4][0] for info in socket.getaddrinfo(host, 443)})
            print(f"dns {host}: {', '.join(addresses[:3])}")
        except (OSError, UnicodeError) as exc:
            print(f"dns {host}: {describe(exc)}")
    for url in urls:
        entry = read_one(url, {})
        if "text" in entry.get("article", {}):
            entry["article"]["text"] = clip(entry["article"]["text"], 300)
        entry["comments"] = [clip(comment["text"], 80) for comment in entry.get("comments", [])]
        print(status_line(entry))
        print(json.dumps(entry, ensure_ascii=False))
    print(f"dns_via_proxy: {sorted(set(DNS_VIA_PROXY))}")


def main(argv: list[str]) -> None:
    if argv[:1] == ["probe"] and len(argv) > 1:
        probe(argv[1:])
        return
    if len(argv) < 2 or not DATE.match(argv[0]):
        print("\n".join(__doc__.strip().splitlines()[2:4]), file=sys.stderr)
        sys.exit(2)
    date, urls = argv[0], list(dict.fromkeys(argv[1:]))
    out = NEWS / "raw" / date / "deep.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    items: dict[str, dict] = {}
    runs: list[dict] = []
    if out.is_file():  # chạy lại với URL mới (thay tin bị bỏ) thì gộp, URL cũ được đọc lại
        previous = json.loads(out.read_text(encoding="utf-8"))
        items = {entry["url"]: entry for entry in previous.get("items", [])}
        runs = previous.get("runs", [])
    started, clock = datetime.now(timezone.utc), time.monotonic()
    done: list[dict] = []

    def write() -> None:
        out.write_text(json.dumps({"date": date, "runs": runs, "items": list(items.values())},
                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def save(entry: dict) -> None:  # ghi sau mỗi URL: Bash timeout hay hết hạn vẫn giữ phần đã đọc
        items[entry["url"]] = entry
        done.append(entry)
        print(status_line(entry), flush=True)
        write()

    def finish() -> None:
        run = run_summary(done, started, time.monotonic() - clock)
        runs.append(run)
        write()
        print(f"TỔNG: {run['summary']}", flush=True)
        print(f"DEEP: {out.relative_to(ROOT)}", flush=True)

    hn_ids = nominated_hn_ids(date)
    pool = ThreadPoolExecutor(max_workers=4)
    futures = {pool.submit(read_one, url, hn_ids): url for url in urls}
    try:
        for future in as_completed(futures, timeout=DEADLINE_SECONDS):
            try:
                save(future.result())
            except Exception as exc:  # lỗi ngoài dự kiến ở 1 URL không được làm mất các URL khác
                save({"url": futures[future], "error": f"{type(exc).__name__}: {exc}"})
    except FuturesTimeout:
        for future, url in futures.items():
            if not future.done():
                save({"url": url, "error": f"quá {DEADLINE_SECONDS}s, bỏ qua"})
        finish()
        os._exit(0)  # thread đang treo không kill được, thoát bình thường sẽ phải đợi chúng
    pool.shutdown()
    finish()


if __name__ == "__main__":
    main(sys.argv[1:])
