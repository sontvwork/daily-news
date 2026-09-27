# Routine setup — Daily News

Cấu hình routine (điền vào `/schedule` hoặc form tại claude.ai/code/routines):

| Mục | Giá trị |
|---|---|
| Tên | `Daily News` |
| Repository | `sontvwork/daily-news` |
| Environment | `daily-news` (Network **Full**, env vars theo README) |
| Lịch | Hằng ngày 07:00 giờ Việt Nam = cron `0 0 * * *` (UTC) |
| Connectors | Bỏ hết, routine không cần connector nào |
| Prompt | Nội dung file [ROUTINE_PROMPT.md](ROUTINE_PROMPT.md) — dán nguyên văn vào ô prompt |

Sửa nội dung prompt thì sửa trong `ROUTINE_PROMPT.md`, sau đó dán lại toàn bộ file đó vào ô prompt của routine trên claude.ai/code/routines.
