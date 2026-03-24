"""
main.py — Entry point for GitHub Actions.

Flow:
  1. Scan Google Drive folder for .mp4 files
  2. Skip any that already have a matching .srt in the same folder
  3. For each unprocessed video:
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
    is_weekday = now.weekday() < 5
    is_work_hours = 10 <= now.hour < 17
    return is_weekday and is_work_hours


def main():
    now = datetime.now(CENTRAL_TZ)
    print(f"🕐 Current time: {now.strftime('%A %B %d, %Y %I:%M %p CT')}")

    if not is_active_hours():
        print("⏸️  Outside active hours (Mon–Fri 10am–5pm CT). Exiting.")
        sys.exit(0)

    if not DRIVE_FOLDER_ID:
        print("❌ DRIVE_FOLDER_ID environment variable not set.")
        sys.exit(1)

    print(f"🚀 Starting scan of Drive folder: {DRIVE_FOLDER_ID}")
    print(f"📧 Recipient: {RECIPIENT_EMAIL}")
    print()

    # Find unprocessed videos
    videos = list_unprocessed_videos(DRIVE_FOLDER_ID)

    if not videos:
        print("✅ Nothing to process — all videos already have .srt files.")
        sys.exit(0)

    success_count = 0
    fail_count = 0

    for video in videos:
        file_id = video['id']
        file_name = video['name']
        size_mb = int(video.get('size', 0)) / (1024 * 1024)

        print(f"\n{'='*60}")
        print(f"🎬 Processing: {file_name} ({size_mb:.1f} MB)")
        print(f"{'='*60}")

        video_path = None
        srt_path = None

        try:
            # Step 1: Download
            video_path = download_video(file_id, file_name)

            # Step 2: Transcribe
            srt_path, base_name = transcribe_to_srt(video_path, model_size='medium')

            # Step 3: Upload .srt back to Drive (backup)
            upload_srt_to_drive(srt_path, DRIVE_FOLDER_ID)

            # Step 4: Email
            send_srt_email(srt_path, file_name, RECIPIENT_EMAIL)

            success_count += 1
            print(f"✅ {file_name} → done!")

        except Exception as e:
            print(f"❌ Failed to process {file_name}: {e}")
            fail_count += 1

        finally:
            # Clean up temp files to keep runner disk usage low
            for path in [video_path, srt_path]:
                if path and os.path.exists(path):
                    os.remove(path)
                    print(f"🗑️  Cleaned up: {os.path.basename(path)}")

    print(f"\n{'='*60}")
    print(f"🏁 Done. {success_count} succeeded, {fail_count} failed.")

    if fail_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
