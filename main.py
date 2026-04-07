"""
main.py — Entry point for GitHub Actions.

Flow:
  1. Check active hours (Mon–Fri 10am–5pm CT) — exit early if outside
  2. Scan Drive folder for .mp4 files not yet fully processed
  3. A video is "fully done" only if all processing steps succeeded:
       transcribed → auto-aligned → .srt uploaded to Drive → emailed
     This is tracked by a .sent marker file in Drive (e.g. 03_26_26.sent)
  4. For each unprocessed video:
     a. Download from Drive
     b. Transcribe with Whisper (medium)
      c. Auto-align the .srt so the first spoken subtitle starts at 00:00:00,000
      d. Upload .srt back to Drive
      e. Email .srt to recipient
      f. Upload .sent marker to Drive (confirms full completion)
      g. Clean up local temp files
  5. If no videos found → exit immediately (cron re-triggers in 5 min)
  6. If a step fails → no .sent written → video retried next run
"""

import os
import sys
import pytz
from datetime import datetime
from dotenv import load_dotenv

from downloader import list_unprocessed_videos, download_video, upload_srt_to_drive, mark_as_sent
from transcriber import transcribe_to_srt
from emailer import send_srt_email
from subtitle_adjuster import format_timestamp, shift_srt_to_zero

load_dotenv()

DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')
RECIPIENT_EMAIL  = os.environ.get('RECIPIENT_EMAIL', 'jiajun@livebash.com')
CENTRAL_TZ       = pytz.timezone('America/Chicago')


def is_active_hours():
    """Returns True if current time is Mon–Fri 10am–5pm Central."""
    now = datetime.now(CENTRAL_TZ)
    return now.weekday() < 5 and 10 <= now.hour < 17


def process_video(video):
    """
    Run all processing steps for one video:
      1. Download from Drive
      2. Transcribe with Whisper → .srt file
      3. Auto-align subtitles so the first spoken cue starts at 00:00:00,000
      4. Upload .srt to Drive
      5. Email .srt to recipient
      6. Upload .sent marker (only if all above succeed)

    Returns True if fully complete, False if any step failed.
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
        print("   ✅ Step 1/5 — Downloaded")

        # Step 2: Transcribe
        srt_path, base_name = transcribe_to_srt(video_path, model_size='medium')
        print("   ✅ Step 2/5 — Transcribed")

        # Step 3: Auto-align subtitles to the first spoken cue
        shift_ms, first_cue_text = shift_srt_to_zero(srt_path)
        if shift_ms > 0:
            print(f"   ✅ Step 3/5 — Auto-aligned subtitles by {format_timestamp(shift_ms)}")
            if first_cue_text:
                print(f"      First cue at zero: {first_cue_text}")
        else:
            print("   ✅ Step 3/5 — No timestamp adjustment needed")

        # Step 4: Upload .srt to Drive
        upload_srt_to_drive(srt_path, DRIVE_FOLDER_ID)
        print("   ✅ Step 4/5 — .srt uploaded to Drive")

        # Step 5: Email
        send_srt_email(srt_path, file_name, RECIPIENT_EMAIL)
        print("   ✅ Step 5/5 — Emailed")

        # All steps succeeded — write .sent marker so this video is never re-processed
        mark_as_sent(base_name, DRIVE_FOLDER_ID)
        print(f"✅ {file_name} → fully complete!")
        return True

    except Exception as e:
        print(f"❌ Error processing {file_name}: {e}")
        print("   ⚠️  No .sent marker written — will retry next run")
        return False

    finally:
        # Always clean up local temp files regardless of success/failure
        for path in [video_path, srt_path]:
            if path and os.path.exists(path):
                os.remove(path)
                print(f"🗑️  Cleaned up: {os.path.basename(path)}")


def main():
    now = datetime.now(CENTRAL_TZ)
    print(f"🕐 Current time: {now.strftime('%A %B %d, %Y %I:%M %p CT')}")

    # Gate 1: Active hours check
    if not is_active_hours():
        print("💤 Outside active hours (Mon–Fri 10am–5pm CT). Exiting.")
        sys.exit(0)

    # Gate 2: Env var check
    if not DRIVE_FOLDER_ID:
        print("❌ DRIVE_FOLDER_ID environment variable not set.")
        sys.exit(1)

    print(f"🚀 Scanning Drive folder: {DRIVE_FOLDER_ID}")
    print(f"📧 Recipient: {RECIPIENT_EMAIL}")
    print()

    # Find videos not yet fully processed (no matching .sent file)
    videos = list_unprocessed_videos(DRIVE_FOLDER_ID)

    if not videos:
        print("✅ Nothing to process — all videos fully complete.")
        print("   (cron will re-check in 5 minutes)")
        sys.exit(0)

    success_count = 0
    fail_count    = 0

    for video in videos:
        if process_video(video):
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
