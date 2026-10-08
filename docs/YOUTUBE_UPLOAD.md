# YouTube Upload — History Snooze

Workflow `.github/workflows/upload_youtube.yml` uploads a rendered master to
YouTube via the Data API v3, sets metadata + custom thumbnail, and optionally
schedules the publish time. Triggered manually via **Actions → HistorySnooze
YouTube Upload → Run workflow**.

## One-time setup (do this once)

### 1. Google Cloud project + OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/), create (or reuse)
   a project, and enable **YouTube Data API v3**.
2. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Note the **Client ID** and **Client secret**.
3. Get a refresh token (run once on any machine with Python):
   ```bash
   pip install google-auth-oauthlib
   python3 - <<'EOF'
   from google_auth_oauthlib.flow import InstalledAppFlow
   flow = InstalledAppFlow.from_client_config(
       {"installed": {"client_id": "<CLIENT_ID>",
                      "client_secret": "<CLIENT_SECRET>",
                      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                      "token_uri": "https://oauth2.googleapis.com/token"}},
       scopes=["https://www.googleapis.com/auth/youtube.upload"])
   creds = flow.run_local_server(port=8080)
   print("REFRESH_TOKEN:", creds.refresh_token)
   EOF
   ```
   Sign in with the **channel owner account** (`aleron.dt@gmail.com`) when the
   browser opens, and copy the printed refresh token.

### 2. GitHub Secrets (repo → Settings → Secrets and variables → Actions)

| Secret             | Value                          |
|--------------------|--------------------------------|
| `YT_CLIENT_ID`     | OAuth client ID from step 1    |
| `YT_CLIENT_SECRET` | OAuth client secret from step 1|
| `YT_REFRESH_TOKEN` | Refresh token from step 1      |

> Do NOT commit these to the repo. The workflow reads them only from secrets.

Optional (only if `video_source` starts with `drive:` and the file is not
publicly shareable):
| `GDRIVE_SA_JSON` | Service-account JSON for Drive download |

## Usage

**Actions → HistorySnooze YouTube Upload → Run workflow**, fill in:

| Input                | Example |
|----------------------|---------|
| `video_source`       | `drive:1AbC...` (Drive file ID) or `artifact:37733630699/master` |
| `title`              | `Emperor Nero — The Darkest Midnight Before the Fall of Rome` |
| `description`        | Full description text |
| `tags`               | `history, sleep story, bedtime stories` |
| `thumbnail_drive_id` | Drive file ID of the 1280×720 thumbnail (optional) |
| `schedule_time`      | `2026-10-12T21:00:00+07:00` — video stays private until then |
| `visibility`         | Used only when `schedule_time` is empty: `public` / `unlisted` / `private` |

The workflow reports the **video ID and watch URL** in the run summary.

## Notes

- `publishAt` only works with `privacyStatus=private` — the script enforces this
  automatically when `schedule_time` is set.
- One upload costs ~1,600 API quota units (default project quota: 10,000/day).
- Uploads are resumable (32 MB chunks); a runner restart mid-upload will not
  corrupt the video, but the workflow step itself is not auto-retried.
- Local dry-run (no token needed):
  `python3 tools/youtube_upload.py --video v.mp4 --title "T" --dry-run`
