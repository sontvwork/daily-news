# Daily News

Bản tin tiếng Việt hằng ngày về **AI ứng dụng trong phát triển phần mềm** (Claude Code, Cursor, Copilot, Antigravity, AI agents cho testing/review/DevOps, tin gọi vốn về dev tool). Nội dung tổng hợp từ Reddit, Hacker News, X, YouTube, GitHub và web thông qua skill [last30days](https://github.com/mvanhorn/last30days-skill).

- 🌐 Trang: https://sontvwork.github.io/daily-news/
- 📡 Atom feed: https://sontvwork.github.io/daily-news/feed.xml

```
Claude Code Routine (07:00 VN = cron 0 0 * * * UTC, cloud)
  → scripts/research.sh: last30days --discover (3 leg, --days 1) cho từng domain → news/raw/
  → Claude viết news/YYYY-MM-DD.md (tiếng Việt) + 3 dòng tóm tắt
  → scripts/publish.sh: library feed → guard → commit "news: DATE" → push main
      → GitHub Actions deploy news/ lên Pages → kiểm tra link live → Google Chat
  (lỗi ở bất kỳ bước nào → Google Chat báo bước bị fail)
GitHub Actions watchdog 08:30 VN: chưa có bản tin hôm nay → Google Chat
```

## Cấu trúc

| Đường dẫn | Vai trò |
|---|---|
| `.claude/skills/last30days/` | Skill vendored, pin commit trong `.vendored-from` |
| `config/news.env` | Cấu hình không bí mật: domain, lookback, URL Pages |
| `scripts/research.sh` | Wrapper engine: `preflight`, `nominate`, `research`, `finalize`, `oneshot`, `status` |
| `scripts/news.py` | `validate`, `site` (library feed + kiểm tra link), `link`, `summary`, `verify-live` |
| `scripts/guard.sh` | Hàng rào an toàn: chỉ cho phép thay đổi trong `news/`, không xoá, không lộ secret |
| `scripts/publish.sh` | Cách duy nhất để commit/push; mọi lỗi đều gửi Google Chat |
| `scripts/notify.sh` | Google Chat webhook (`jq` + `curl`), hỗ trợ `DRY_RUN=1` |
| `news/` | Site root: `YYYY-MM-DD.md`, `raw/`, `index.html`, `feed.xml`, `briefs/` |
| `ROUTINE_PROMPT.md` | Prompt dán vào routine |

**Vì sao vendor skill:** cloud session không cài plugin, kể cả plugin khai báo trong `.claude/settings.json`. Nó chỉ dùng được skill đã commit trong repo. Docs không xác nhận cloud có clone submodule, còn setup script thì bị cache và phiên bản có thể trôi. Vendor pin cứng một commit và không cần mạng lúc chạy.

## Setup từ đầu

### 1. Google Chat incoming webhook
1. Mở Space nhận tin → tên Space → **Apps & integrations** → **Webhooks** → **Add webhook**.
2. Đặt tên `Daily News`, rồi **Save** và copy URL (dạng `https://chat.googleapis.com/v1/spaces/.../messages?key=...&token=...`).
3. URL này là **secret**: chỉ lưu trong env của cloud environment, GitHub secret và `.env.local` (local, đã gitignore). Tuyệt đối không commit.

### 2. GitHub repo + Pages
1. Repo `sontvwork/daily-news` (public).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**. Workflow `.github/workflows/pages.yml` deploy thư mục `news/` mỗi lần có push vào `main` chạm `news/**`.
3. **Không** bật branch protection hay ruleset cho `main`. Nếu bật, routine sẽ bị từ chối push.
4. Mọi commit trên `main` phải do chính tài khoản sở hữu routine author (xem mục 6). Repo này đặt `user.email` cục bộ là email noreply của `sontvwork`.
5. **Settings → Secrets and variables → Actions → New repository secret**: `GCHAT_WEBHOOK_URL` = URL webhook. Workflow watchdog dùng secret này.

### 3. Cloud environment
Vào [claude.ai/code](https://claude.ai/code) → chọn environment → **Add cloud environment** (hoặc icon settings của environment có sẵn). Đặt tên `daily-news`, rồi cấu hình:
- **Network access: Full.** Mức **Trusted** mặc định chặn reddit, HN, YouTube, polymarket… (lỗi `403 host_not_allowed`). `chat.googleapis.com` thì đã nằm sẵn trong `*.googleapis.com`. Nếu muốn dùng **Custom**, phải liệt kê đủ domain của mọi nguồn và tick **Also include default list of common package managers**.
- **Environment variables** (mỗi dòng `KEY=value`):
  ```
  SETUP_COMPLETE=true
  GCHAT_WEBHOOK_URL=<url webhook>
  SCRAPECREATORS_API_KEY=<key>      # tuỳ chọn: dự phòng Reddit/YouTube khi IP cloud bị chặn, nguồn X
  XAI_API_KEY=<key>                 # tuỳ chọn: nguồn X/Twitter không cần cookie
  BRAVE_API_KEY=<key>               # tuỳ chọn: web search
  ```
  ⚠️ Ai dùng chung environment này đều đọc được các biến trên, nên hãy giữ environment ở chế độ riêng tư. Mục **API credentials** (chỉ có trên Pro/Max) không dùng được cho webhook, vì key của webhook nằm trong URL chứ không nằm trong header. Engine cũng chỉ bật nguồn khi thấy key trong env, nên các API key vẫn phải để ở env vars. **Không** đưa `AUTH_TOKEN`/`CT0` (cookie X) lên cloud.
- **Setup script**: dán nội dung `scripts/setup_cloud.sh`.

### 4. Quyền GitHub cho routine
Cài [Claude GitHub App](https://github.com/apps/claude) cho repo, hoặc chạy `/web-setup` trong Claude Code CLI.

### 5. Tạo routine
- **CLI**: chạy `/schedule` trong một session Claude Code *local* (lệnh này không có trong cloud session). Hoặc làm trên web tại [claude.ai/code/routines](https://claude.ai/code/routines) → **New routine**.
- Dán prompt nằm giữa hai dòng `8<` trong [`ROUTINE_PROMPT.md`](ROUTINE_PROMPT.md). Chọn repo `sontvwork/daily-news` và environment `daily-news`. Ở mục **Connectors**, bỏ hết connector.
- Trigger: **Schedule → Daily, 07:00** (giờ local). Muốn đặt cron chính xác thì chạy `/schedule update` và nhập `0 0 * * *` (UTC). Kiểm tra next run hiển thị đúng 07:00 giờ Việt Nam. Lịch đặt đúng giờ chẵn có thể chạy trễ vài phút; ngày của bản tin luôn tính theo `Asia/Ho_Chi_Minh` nên không bị ảnh hưởng.

### 6. Quyền push thẳng `main` (về toggle "Allow unrestricted branch pushes")
Docs Routines hiện tại (research preview, kiểm tra ngày 26/09/2026) **không còn toggle này**. Hành vi thực tế như sau:
- Mặc định routine push lên branch `claude/*`.
- Khi prompt chỉ định branch khác (ở đây là `main`), Claude Code kiểm tra trước khi push và **từ chối** nếu:
  - branch bị protect trên GitHub;
  - có người khác đang mở PR từ branch đó;
  - branch có commit do người khác author.
- GitHub proxy của cloud chỉ cho push branch đang checkout. Vì vậy prompt yêu cầu ở lại `main`, và `publish.sh` kiểm tra điều đó.

Nếu UI của bạn vẫn hiện toggle **Allow unrestricted branch pushes** (thường nằm trong phần repository của form routine), hãy bật nó lên.

## Chạy thử thủ công
- **Cloud**: trang routine → **Run now**, hoặc `/schedule run` trong CLI. Mở session của run để đọc transcript. Lưu ý: chấm xanh chỉ có nghĩa là session không gặp lỗi hạ tầng.
- **Local** (macOS/Linux, Python ≥ 3.12, `jq`):
  ```bash
  printf 'GCHAT_WEBHOOK_URL=%s\n' '<url>' > .env.local && chmod 600 .env.local   # bỏ bước này để dry-run
  bash scripts/research.sh preflight
  # Mở Claude Code trong repo và yêu cầu: "Làm theo prompt trong ROUTINE_PROMPT.md"
  # Hoặc tự chạy từng lệnh trong ROUTINE_PROMPT.md.
  DATE=$(TZ=Asia/Ho_Chi_Minh date +%F)
  bash scripts/publish.sh "$DATE" --no-push                                  # build + guard, tin nhắn ở chế độ dry-run
  DRY_RUN=1 bash scripts/notify.sh failure "$DATE" test 'thử "ký tự" đặc biệt'
  ```
  Config local của last30days (`~/.config/last30days/.env`) có thể bật nhiều nguồn hơn trên cloud.

## Vận hành
- **Đổi chủ đề / cửa sổ thời gian**: sửa `config/news.env` (`DOMAINS`, `LOOKBACK_DAYS`) bằng tay. Routine không được sửa file này.
- **Cập nhật skill**: `scripts/vendor_skill.sh [ref]`, review diff rồi commit tay.
- **Chạy lại trong ngày**: `news/YYYY-MM-DD.md` bị ghi đè, không sinh file trùng. Tên trang bài ổn định nên `library feed` không phải xoá trang nào.
- **Thứ bị chặn bởi guard**: file ngoài `news/`, xoá hoặc đổi tên file, merge commit, commit message khác `news: YYYY-MM-DD`, secret nằm trong nội dung.

## Rủi ro đã biết
- IP datacenter của cloud dễ bị Reddit/YouTube chặn. ScrapeCreators đỡ được một phần. Xem `bash scripts/research.sh status <slug> <DATE>`.
- `--days 1` và ngưỡng tin cậy của engine khiến có ngày ra "không có tin mới nổi bật". Đây là kết quả hợp lệ.
- Routines đang research preview: UI, giới hạn và quy tắc push có thể thay đổi. Routine tính vào hạn mức run mỗi ngày của tài khoản.
- Cron của GitHub Actions (watchdog) có thể trễ vài phút đến vài chục phút.
- Trang Pages của repo public ai cũng xem được.
