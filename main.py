"""
main.py — Entry point for GitHub Actions.

Flow:
  1. Check active hours (Mon–Fri 10am–5pm CT) — exit early if outside
  2. Scan Drive folder for .mp4 files
  3. Load processed_log.txt from Drive (tracks fully completed videos)
  4. Skip any video already in the log (transcribed + uploaded + emailed)
  5. For each unprocessed video:
     a. Download from Drive
     b. Transcribe with Whisper (medium)
     c. Upload .srt back to Drive
     d. Email .srt to recipient
     e. Mark as done in processed_log.txt on Drive
     f. Clean up local temp files
"""

import os
import sys
import io
import pytz
from datetime import datetime
from dotenv import load_dotenv

from downloader import (
    list_all_videos, download_video, upload_srt_to_drive,
    load_processed_log, save_processed_log, get_drive_service
)
from transcriber import transcribe_to_srt
from emailer import send_srt_email

load_dotenv()

DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')
RECIPIENT_EMAIL  = os.environ.get('RECIPIENT_EMAIL', 'jiajun@livebash.com')
CENTRAL_TZ       = pytz.timezone('America/Chicago')


def is_active_hours():
    """Returns True if Mon–Fri 10am–5pm Central."""
    now = datetime.now(CENTRAL_TZ)
    return now.weekday() < 5 and 10 <= now.hour < 17


def process_video(video, processed_log):
    """
    Download, transcribe, upload, email one video.
    Only marks as done if ALL steps succeed.
    Returns True on full success.
    """
    file_id   = video['id']
    file_name = video['name']
    size_mb   = int(video.get('size', 0)) / (1024 * 1024)

    print(f"\n{'='*60}")
    print(f"🎬 Processing: {file_name} ({size_mb:.1f} MB)")
    print(f"{'='*60}")

    video_path = None
    srt_path   = None

    try:
        # Step 1: Download
        video_path = download_video(file_id, file_name)
        print(f"   ✅ Step 1/3 — Downloaded")

        # Step 2: Transcribe
        srt_path, base_name = transcribe_to_srt(video_path, model_size='medium')
        print(f"   ✅ Step 2/3 — Transcribed")

        # Step 3: Upload .srt to Drive
        upload_srt_to_drive(srt_path, DRIVE_FOLDER_ID)
        print(f"   ✅ Step 3a — Uploaded to Drive")

        # Step 4: Email
        send_srt_email(srt_path, file_name, RECIPIENT_EMAIL)
        print(f"   ✅ Step 3b — Emailed")

        # ALL steps succeeded — mark as done in log
        processed_log.add(file_name)
        save_processed_log(processed_log, DRIVE_FOLDER_ID)
        print(f"   ✅ Marked as fully done in processed_log.txt")
        print(f"✅ {file_name} → complete!")
        return True

    except Exception as e:
        print(f"❌ Failed during processing of {file_name}: {e}")
        print(f"   ⚠️  NOT marked as done — will retry next run")
        return False

    finally:
        for path in [video_path, srt_path]:
            if path and os.path.exists(path):
                os.remove(path)
                print(f"🗑️  Cleaned up: {os.path.basename(path)}")


def main():
    now = datetime.now(CENTRAL_TZ)
    print(f"🕐 Current time: {now.strftime('%A %B %d, %Y %I:%M %p CT')}")

    if not is_active_hours():
        print("💤 Outside active hours (Mon–Fri 10am–5pm CT). Exiting.")
        sys.exit(0)

    if not DRIVE_FOLDER_ID:
        print("❌ DRIVE_FOLDER_ID environment variable not set.")
        sys.exit(1)

    print(f"🚀 Scanning Drive folder: {DRIVE_FOLDER_ID}")
    print(f"📧 Recipient: {RECIPIENT_EMAIL}")

    # Load the log of fully-completed videos from Drive
    processed_log = load_processed_log(DRIVE_FOLDER_ID)
    print(f"📋 {len(processed_log)} video(s) already fully processed in log")

    # Get all .mp4s, filter out ones already fully done
    all_videos  = list_all_videos(DRIVE_FOLDER_ID)
    unprocessed = [v for v in all_videos if v['name'] not in processed_log]

    print(f"📂 Found {len(all_videos)} total video(s), "
          f"{len(unprocessed)} need processing")

    if not unprocessed:
        print("✅ Nothing to process — all videos fully completed "
              "(transcribed + uploaded + emailed).")
        sys.exit(0)

    success_count = 0
    fail_count    = 0

    for video in unprocessed:
        if process_video(video, processed_log):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n{'='*60}")
    print(f"🏁 Done. {success_count} succeeded, {fail_count} failed.")
    if fail_count > 0:
        print(f"⚠️  {fail_count} video(s) will be retried next run.")
        sys.exit(1)


if __name__ == '__main__':
    main()
