"""
main.py — Entry point for GitHub Actions.

Flow:
  1. Check active hours (Mon–Fri 10am–5pm CT) — exit early if outside
  2. Scan Drive folder for unprocessed .mp4 files
  3. If none found, exit immediately (cron re-triggers in 5 min)
  4. For each unprocessed video:
     a. Download from Drive
     b. Transcribe with Whisper (medium)
     c. Upload .srt back to the same Drive folder (backup)
     d. Email .srt to recipient
     e. Clean up local temp files
"""

import os
import sys
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

    # FIX 1: Active hours gate — exits immediately if outside Mon–Fri 10am–5pm CT
    if not is_active_hours():
        print("💤 Outside active hours (Mon–Fri 10am–5pm CT). Exiting.")
        sys.exit(0)

    if not DRIVE_FOLDER_ID:
        print("❌ DRIVE_FOLDER_ID environment variable not set.")
        sys.exit(1)

    print(f"🚀 Scanning Drive folder: {DRIVE_FOLDER_ID}")
    print(f"📧 Recipient: {RECIPIENT_EMAIL}")

    videos = list_unprocessed_videos(DRIVE_FOLDER_ID)

    # FIX 2: Exit immediately if nothing to do — cron will re-trigger in 5 min
    if not videos:
        print("✅ Nothing to process — all videos already have .srt files.")
        sys.exit(0)

    success_count = 0
    fail_count = 0

    for video in videos:
        if process_video(video):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n{'='*60}")
    print(f"🏁 Done. {success_count} succeeded, {fail_count} failed.")

    if fail_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()