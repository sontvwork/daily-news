# Daily News

Bản tin tiếng Việt hằng ngày về **AI ứng dụng trong phát triển phần mềm**. Nội dung tổng hợp từ Reddit, Hacker News, X, YouTube và web thông qua skill [last30days](https://github.com/mvanhorn/last30days-skill).

- 🌐 Trang: https://sontvwork.github.io/daily-news/

```
Claude Code Routine (07:00 VN = cron 0 0 * * * UTC, cloud)
  → scripts/research.sh: last30days --discover (3 leg, --days 1) cho từng domain → news/raw/
  → Claude viết news/YYYY-MM-DD.md (tiếng Việt) + 1–3 dòng tóm tắt
  → scripts/publish.sh: xoá bản tin quá 30 ngày → feed.xml (library feed) + trang card (theme/) → guard → commit "news: DATE" → push main
      → GitHub Actions deploy news/ lên Pages → kiểm tra link live → Google Chat
  (lỗi ở bất kỳ bước nào → Google Chat báo bước bị fail)
GitHub Actions watchdog 08:30 VN: chưa có bản tin hôm nay → Google Chat
```

## Cấu trúc


| Đường dẫn                       | Vai trò                                                                                                            |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `.claude/skills/last30days/`        | Skill vendored, pin commit trong`.vendored-from`                                                                    |
| `config/news.env`                   | Cấu hình không bí mật: domain, lookback, số ngày lưu trữ (`RETENTION_DAYS`), URL Pages                       |
| `scripts/research.sh`               | Wrapper engine:`preflight`, `nominate`, `research`, `finalize`, `oneshot`, `status`                                 |
| `scripts/news.py`                   | `validate`, `prune` (xoá bản tin quá hạn), `site` (feed.xml + render trang + kiểm tra link), `link`, `summary`, `verify-live` |
| `scripts/site_render.py` + `theme/` | Renderer riêng: template`index.html`, `brief.html`, `404.html`, `style.css` (card dashboard, light/dark)           |
| `scripts/guard.sh`                  | Hàng rào an toàn: chỉ cho phép thay đổi trong`news/`, không xoá (trừ bản tin quá hạn), không lộ secret     |
| `scripts/publish.sh`                | Cách duy nhất để commit/push; mọi lỗi đều gửi Google Chat                                                  |
| `scripts/dev.sh`                    | Chạy lại ở local để test (`build`, `notify`): không commit/push, guard chỉ cảnh báo, Google Chat mặc định dry-run |
| `scripts/notify.sh`                 | Google Chat webhook (`jq` + `curl`), hỗ trợ `DRY_RUN=1`                                                           |
| `news/`                             | Site root:`YYYY-MM-DD.md`, `raw/YYYY-MM-DD/`, `index.html`, `404.html`, `feed.xml`, `briefs/`, `assets/style.css` (bản copy từ `theme/`) |
| `ROUTINE_PROMPT.md`                 | Prompt dán vào routine                                                                                            |
| `ROUTINE_SETUP.md`                  | Cấu hình routine (tên, lịch, environment) — trỏ đến `ROUTINE_PROMPT.md`                                          |

## Setup từ đầu

### 1. Google Chat incoming webhook

1. Mở Space nhận tin → tên Space → **Apps & integrations** → **Webhooks** → **Add webhook**.
2. Đặt tên, chọn icon rồi **Save** và copy URL (dạng `https://chat.googleapis.com/v1/spaces/.../messages?key=...&token=...`).
3. URL này là **secret**: chỉ lưu trong env của cloud environment, GitHub secret và `.env.local` (local, đã gitignore). Tuyệt đối không commit.

### 2. GitHub repo + Pages

1. Repo `sontvwork/daily-news` (public).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**. Workflow `.github/workflows/pages.yml` deploy thư mục `news/` mỗi lần có push vào `main` chạm `news/**`.
3. **Không** bật branch protection hay ruleset cho `main`. Nếu bật, routine sẽ bị từ chối push.
4. Mọi commit trên `main` phải do chính tài khoản sở hữu routine author (xem mục 6). Repo này đặt `user.email` cục bộ là email noreply của `sontvwork`.
5. **Settings → Secrets and variables → Actions → New repository secret**: `GCHAT_WEBHOOK_URL` = URL webhook. Workflow watchdog dùng secret này.

### 3. Quyền GitHub cho routine

Cài [Claude GitHub App](https://github.com/apps/claude) cho repo, hoặc chạy `/web-setup` trong Claude Code CLI.

### 4. Tạo routine

- Chạy `/schedule` trong một session Claude Code *local* (lệnh này không có trong cloud session). Hoặc làm trên web tại [claude.ai/code/routines](https://claude.ai/code/routines) → **New routine**.
- Dán nguyên nội dung [`ROUTINE_PROMPT.md`](ROUTINE_PROMPT.md) vào ô prompt. Cấu hình còn lại (tên, repo, lịch, connectors) xem [`ROUTINE_SETUP.md`](ROUTINE_SETUP.md). Chọn repo `sontvwork/daily-news`. Ở mục **Connectors**, bỏ hết connector.
- Cloud environment nằm ngay trong form tạo routine này (không phải một mục riêng trên claude.ai/code), làm ngay sau khi dán prompt. Đặt tên `daily-news`, rồi cấu hình:
  - **Network access: Full.** Mức **Trusted** mặc định chặn reddit, Hacker News, YouTube, polymarket… (lỗi `403 host_not_allowed`). `chat.googleapis.com` thì đã nằm sẵn trong `*.googleapis.com`. Nếu muốn dùng **Custom**, phải liệt kê đủ domain của mọi nguồn và tick **Also include default list of common package managers**.
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
- Trigger: **Schedule → Daily, 07:00** (giờ local). Muốn đặt cron chính xác thì chạy `/schedule update` và nhập `0 0 * * *` (UTC). Kiểm tra next run hiển thị đúng 07:00 giờ Việt Nam. Lịch đặt đúng giờ chẵn có thể chạy trễ vài phút; ngày của bản tin luôn tính theo `Asia/Ho_Chi_Minh` nên không bị ảnh hưởng.

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

  Chạy lại để test (không commit/push, code chưa commit vẫn chạy được):

  ```bash
  # Viết lại bài: yêu cầu Claude Code "Chạy lại bước viết bài cho $DATE" (dữ liệu: news/raw/$DATE/), rồi:
  bash scripts/dev.sh build  "$DATE"          # validate → prune → build → guard (chỉ cảnh báo) → notify dry-run
  bash scripts/dev.sh notify "$DATE" --send   # chỉ gửi lại tin Google Chat thật, tiền tố "[TEST] "
  git checkout -- news/ && git clean -fd news/  # bỏ kết quả test
  ```

  Config local của last30days (`~/.config/last30days/.env`) có thể bật nhiều nguồn hơn trên cloud.

## Vận hành

- **Đổi chủ đề / cửa sổ thời gian**: sửa `config/news.env` (`DOMAINS`, `LOOKBACK_DAYS`) bằng tay. Routine không được sửa file này.
- **Đổi giao diện**: sửa `theme/style.css`, `theme/index.html`, `theme/brief.html` (placeholder `$tên` của `string.Template`). HTML của từng card nằm trong `scripts/site_render.py`. Xem thử bằng `python3 scripts/news.py site <DATE>` rồi mở `news/index.html`, sau đó commit tay; lần chạy kế tiếp routine sẽ render lại mọi trang theo theme mới. `library feed` của engine giờ chỉ dùng để tạo `feed.xml`: nó chạy trong thư mục tạm, và tên trang bài lấy từ feed nên link cũ không đổi.
- **Cập nhật skill**: `scripts/vendor_skill.sh [ref]`, review diff rồi commit tay.
- **Chạy lại trong ngày**: `news/YYYY-MM-DD.md` bị ghi đè, không sinh file trùng. Tên trang bài ổn định nên `library feed` không phải xoá trang nào.
- **Lưu trữ 30 ngày**: mỗi lần publish, `news.py prune` xoá `.md`, `raw/` và trang bài của các ngày cũ hơn `RETENTION_DAYS` (tính lùi từ DATE của bản tin), gộp vào commit `news: DATE`. Chỉ xoá khỏi `main` và site, history git vẫn giữ. Link cũ trong Google Chat mở ra trang `404.html` "bản tin đã quá hạn lưu trữ".
- **Thứ bị chặn bởi guard**: file ngoài `news/`, xoá hoặc đổi tên file (trừ file có ngày của bản tin đã quá hạn), merge commit, commit message khác `news: YYYY-MM-DD`, secret nằm trong nội dung.

## Rủi ro đã biết

- GitHub không dùng được làm nguồn trên cloud: proxy của sandbox chỉ cho gọi `repos/{owner}/{repo}/...` của repo gắn với session, còn `/search/*` luôn trả 403 *"sessions are bound to their configured repositories"*. Proxy thay header Authorization, nên đổi token/PAT hay thêm repo cho GitHub App đều vô ích. Vì vậy `EXCLUDE_SOURCES` mặc định có `github`.
- Nguồn X trên cloud chỉ bật khi có `XAI_API_KEY` hoặc `SCRAPECREATORS_API_KEY` trong env (xem bước 4). Nếu thiếu, `research.sh preflight` sẽ không liệt kê `x`.
- IP datacenter của cloud dễ bị Reddit/YouTube chặn. ScrapeCreators đỡ được một phần. Xem `bash scripts/research.sh status <slug> <DATE>`.
- `--days 1` và ngưỡng tin cậy của engine khiến có ngày ra "không có tin mới nổi bật". Đây là kết quả hợp lệ.
- Routines đang research preview: UI, giới hạn và quy tắc push có thể thay đổi. Routine tính vào hạn mức run mỗi ngày của tài khoản.
- Cron của GitHub Actions (watchdog) có thể trễ vài phút đến vài chục phút.
- Trang Pages của repo public ai cũng xem được.
