"""
main.py — Entry point for GitHub Actions.

Flow:
  1. Check active hours (Mon–Fri 10am–5pm CT) — exit early if outside
  2. Loop for ~55 minutes, polling Drive every 60 seconds
  3. For each unprocessed video found:
     a. Download from Drive
     b. Transcribe with Whisper (medium)
     c. Upload .srt back to the same Drive folder (backup)
     d. Email .srt to recipient
     e. Clean up local temp files
"""

import os
import sys
import time
import pytz
from datetime import datetime
from dotenv import load_dotenv

from downloader import list_unprocessed_videos, download_video, upload_srt_to_drive
from transcriber import transcribe_to_srt
from emailer import send_srt_email

load_dotenv()

DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', 'jiajun@livebash.com')
CENTRAL_TZ = pytz.timezone('America/Chicago')

# How long to keep the job alive (55 min = under GitHub's 60 min timeout)
JOB_DURATION_SECONDS = 55 * 60
# How long to wait between Drive scans when no videos are found
POLL_INTERVAL_SECONDS = 60


def is_active_hours():
    """Returns True if Mon–Fri 10am–5pm Central."""
    now = datetime.now(CENTRAL_TZ)
    is_weekday = now.weekday() < 5       # 0=Mon, 4=Fri
    is_work_hours = 10 <= now.hour < 17  # 10am up to (not including) 5pm
    return is_weekday and is_work_hours


def process_video(video):
    """Download, transcribe, upload, email one video. Returns True on success."""
    file_id = video['id']
    file_name = video['name']
    size_mb = int(video.get('size', 0)) / (1024 * 1024)

    print(f"\n{'='*60}")
    print(f"🎬 Processing: {file_name} ({size_mb:.1f} MB)")
    print(f"{'='*60}")

    video_path = None
    srt_path = None

    try:
        video_path = download_video(file_id, file_name)
        srt_path, base_name = transcribe_to_srt(video_path, model_size='medium')
        upload_srt_to_drive(srt_path, DRIVE_FOLDER_ID)
        send_srt_email(srt_path, file_name, RECIPIENT_EMAIL)
        print(f"✅ {file_name} → done!")
        return True

    except Exception as e:
        print(f"❌ Failed to process {file_name}: {e}")
        return False

    finally:
        # Always clean up temp files to keep runner disk usage low
        for path in [video_path, srt_path]:
            if path and os.path.exists(path):
                os.remove(path)
                print(f"🗑️  Cleaned up: {os.path.basename(path)}")


def main():
    now = datetime.now(CENTRAL_TZ)
    print(f"🕐 Current time: {now.strftime('%A %B %d, %Y %I:%M %p CT')}")

    # ── FIX 1: Active hours gate ──────────────────────────────────────────────
    # Exit immediately if outside Mon–Fri 10am–5pm CT.
    # is_active_hours() was defined before but never called — now it's used.
    if not is_active_hours():
        print("💤 Outside active hours (Mon–Fri 10am–5pm CT). Exiting.")
        sys.exit(0)
    # ─────────────────────────────────────────────────────────────────────────

    if not DRIVE_FOLDER_ID:
        print("❌ DRIVE_FOLDER_ID environment variable not set.")
        sys.exit(1)

    print(f"🚀 Starting scan of Drive folder: {DRIVE_FOLDER_ID}")
    print(f"📧 Recipient: {RECIPIENT_EMAIL}")

    # ── FIX 2: Polling loop ───────────────────────────────────────────────────
    # Instead of exiting when no videos are found, keep the job alive for
    # ~55 minutes and re-scan Drive every 60 seconds. This means a video
    # dropped into Drive mid-run gets picked up immediately, not at the
    # next cron trigger 5 minutes later.
    job_end_time = time.time() + JOB_DURATION_SECONDS
    total_success = 0
    total_fail = 0

    while time.time() < job_end_time:
        # Re-check active hours on every tick (job may span the 5pm boundary)
        if not is_active_hours():
            print("\n💤 Active hours ended. Stopping early.")
            break

        now = datetime.now(CENTRAL_TZ)
        print(f"\n🔍 Scanning at {now.strftime('%I:%M:%S %p CT')}...")

        videos = list_unprocessed_videos(DRIVE_FOLDER_ID)

        if not videos:
            remaining = int(job_end_time - time.time())
            print(f"   ✅ Nothing to process. Waiting {POLL_INTERVAL_SECONDS}s "
                  f"(~{remaining//60}m remaining in job)...")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        # Process every unprocessed video found in this scan
        for video in videos:
            if process_video(video):
                total_success += 1
            else:
                total_fail += 1

        # After processing, immediately re-scan without sleeping
        # in case more videos were added while we were transcribing

    # ─────────────────────────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print(f"🏁 Job complete. {total_success} succeeded, {total_fail} failed.")

    if total_fail > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()