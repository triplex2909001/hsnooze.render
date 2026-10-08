#!/usr/bin/env python3
"""
youtube_upload.py — Upload a video to YouTube via Data API v3.

Used by .github/workflows/upload_youtube.yml for History Snooze.

Auth: OAuth2 refresh token flow. Credentials come from environment:
    YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN

Usage:
    python3 tools/youtube_upload.py \
        --video /path/to/video.mp4 \
        --title "My Title" \
        --description "Long description..." \
        --tags "tag1,tag2,tag3" \
        --thumbnail /path/to/thumb.jpg \
        --schedule "2026-10-10T10:00:00+07:00" \
        --visibility private

    # Dry run (validates args + metadata, no API calls, no token needed):
    python3 tools/youtube_upload.py --video v.mp4 --title "T" --dry-run

Notes:
    - publishAt only takes effect when privacyStatus is "private".
      The video auto-publishes at the scheduled time.
    - Without --schedule, --visibility controls the final state
      (public / unlisted / private).
    - Upload costs ~1600 quota units against the project's 10,000/day.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

CHUNK_SIZE = 32 * 1024 * 1024  # 32 MB resumable chunks
API_SERVICE = "youtube"
API_VERSION = "v3"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Upload video to YouTube via Data API v3")
    p.add_argument("--video", required=True, help="Path to video file (.mp4)")
    p.add_argument("--title", required=True, help="Video title (max 100 chars)")
    p.add_argument("--description", default="", help="Video description")
    p.add_argument("--tags", default="", help="Comma-separated tags")
    p.add_argument("--category-id", default="27",
                   help="YouTube category ID (default 27 = Education)")
    p.add_argument("--thumbnail", default=None, help="Path to custom thumbnail (jpg/png)")
    p.add_argument("--schedule", default=None,
                   help="ISO 8601 publish time, e.g. 2026-10-10T10:00:00+07:00")
    p.add_argument("--visibility", default="private",
                   choices=["public", "unlisted", "private"],
                   help="Final visibility when no --schedule given")
    p.add_argument("--language", default="en", help="Default language code")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate inputs only, make no API calls")
    return p.parse_args(argv)


def build_body(args):
    """Build the videos.insert request body, validating schedule rules."""
    title = args.title[:100]
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    status = {}
    if args.schedule:
        # publishAt REQUIRES privacyStatus=private, else it publishes immediately.
        try:
            dt = datetime.fromisoformat(args.schedule)
        except ValueError:
            raise SystemExit(f"ERROR: --schedule is not valid ISO 8601: {args.schedule}")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        status = {
            "privacyStatus": "private",
            "publishAt": dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "selfDeclaredMadeForKids": False,
        }
    else:
        status = {
            "privacyStatus": args.visibility,
            "selfDeclaredMadeForKids": False,
        }

    return {
        "snippet": {
            "title": title,
            "description": args.description,
            "tags": tags,
            "categoryId": args.category_id,
            "defaultLanguage": args.language,
        },
        "status": status,
    }


def get_authenticated_service():
    """Build an authorized YouTube API client from env credentials."""
    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    refresh_token = os.environ.get("YT_REFRESH_TOKEN")
    missing = [n for n, v in (("YT_CLIENT_ID", client_id),
                              ("YT_CLIENT_SECRET", client_secret),
                              ("YT_REFRESH_TOKEN", refresh_token)) if not v]
    if missing:
        raise SystemExit(f"ERROR: missing env vars: {', '.join(missing)}")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    return build(API_SERVICE, API_VERSION, credentials=creds)


def resumable_upload(youtube, args, body):
    """Upload the video file with resumable chunks, return the video resource."""
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    if not os.path.isfile(args.video):
        raise SystemExit(f"ERROR: video file not found: {args.video}")
    size_mb = os.path.getsize(args.video) / (1024 * 1024)
    print(f"Uploading {args.video} ({size_mb:.1f} MB) in {CHUNK_SIZE // (1024*1024)} MB chunks...")

    media = MediaFileUpload(args.video, mimetype="video/mp4",
                            chunksize=CHUNK_SIZE, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
        except Exception as e:  # resumable: retryable errors are raised per-chunk
            print(f"  chunk error (will retry): {e}", file=sys.stderr)
            continue
        if status:
            print(f"  progress: {int(status.progress() * 100)}%")

    print(f"Upload complete. Video ID: {response['id']}")
    return response


def set_thumbnail(youtube, video_id, thumb_path):
    """Upload a custom thumbnail for the video."""
    from googleapiclient.http import MediaFileUpload

    if not thumb_path:
        return
    if not os.path.isfile(thumb_path):
        print(f"WARNING: thumbnail not found, skipping: {thumb_path}", file=sys.stderr)
        return
    mime = "image/png" if thumb_path.lower().endswith(".png") else "image/jpeg"
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumb_path, mimetype=mime),
    ).execute()
    print(f"Thumbnail set: {thumb_path}")


def main(argv=None):
    args = parse_args(argv)
    body = build_body(args)

    if args.dry_run:
        print("DRY RUN — no API calls made.")
        print("Video:", args.video, f"({'exists' if os.path.isfile(args.video) else 'MISSING'})")
        print("Request body:")
        print(json.dumps(body, indent=2, ensure_ascii=False))
        if args.thumbnail:
            print("Thumbnail:", args.thumbnail,
                  f"({'exists' if os.path.isfile(args.thumbnail) else 'MISSING'})")
        return 0

    youtube = get_authenticated_service()
    video = resumable_upload(youtube, args, body)
    video_id = video["id"]
    set_thumbnail(youtube, video_id, args.thumbnail)

    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"VIDEO_ID={video_id}")
    print(f"VIDEO_URL={url}")
    # Also emit GitHub Actions outputs when running in a workflow
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"video_id={video_id}\n")
            f.write(f"video_url={url}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
