"""
downloader.py — Google Drive download/upload + auth + completion tracking.

Completion tracking uses .sent marker files in Drive:
  - 03_24_26.mp4 is "fully done" when 03_24_26.sent exists in the same folder
  - .sent file is only created after transcribe + upload + email ALL succeed
  - This matches the .sent files already in your Drive folder

Auth split:
  - Drive scanning + downloading → Service Account (never expires)
  - Drive uploading (.srt, .sent) → OAuth token (has storage quota)
  - Gmail sending                 → OAuth token
"""

import os
import io
import json
import base64
import pickle
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaIoBaseUpload


# ── Service Account Auth (scanning + downloading) ─────────────────────────────

def get_drive_service():
    """
    Return a Drive client using Service Account — for scanning and downloading.
    - In GitHub Actions: reads from GOOGLE_SERVICE_ACCOUNT_B64 env var
    - Locally: reads from service_account.json file
    """
    SCOPES = ['https://www.googleapis.com/auth/drive']

    sa_b64 = os.environ.get('GOOGLE_SERVICE_ACCOUNT_B64')
    if sa_b64:
        sa_info = json.loads(base64.b64decode(sa_b64).decode('utf-8'))
    elif os.path.exists('service_account.json'):
        with open('service_account.json', 'r') as f:
            sa_info = json.load(f)
    else:
        raise RuntimeError(
            "No service account credentials found.\n"
            "Either set GOOGLE_SERVICE_ACCOUNT_B64 in GitHub Secrets,\n"
            "or place service_account.json in the project folder for local use."
        )

    credentials = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=credentials)


# ── OAuth Auth (uploading + Gmail) ────────────────────────────────────────────

def get_oauth_credentials():
    """
    Load OAuth credentials for uploading to Drive and sending Gmail.
    - In GitHub Actions: reads from GOOGLE_TOKEN_B64 env var
    - Locally: reads from token.pickle file
    """
    creds = None

    token_b64 = os.environ.get('GOOGLE_TOKEN_B64')
    if token_b64:
        creds = pickle.loads(base64.b64decode(token_b64))
    elif os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        raise RuntimeError(
            "No valid OAuth credentials found.\n"
            "Run auth_setup.py locally to generate token.pickle,\n"
            "then encode it as GOOGLE_TOKEN_B64 in GitHub Secrets."
        )
    return creds


def get_drive_upload_service():
    """Return a Drive client using OAuth — for uploading files."""
    return build('drive', 'v3', credentials=get_oauth_credentials())


def get_gmail_service():
    """Return an authenticated Gmail API client."""
    return build('gmail', 'v1', credentials=get_oauth_credentials())


# ── Drive scanning ────────────────────────────────────────────────────────────

def list_unprocessed_videos(folder_id):
    """
    Scan the Drive folder and return .mp4 files that have NOT been fully processed.

    A video is considered fully done only if a matching .sent file exists:
      03_24_26.mp4 → done if 03_24_26.sent exists
      03_25_26.mp4 → done if 03_25_26.sent exists

    This means: transcribed + .srt uploaded + email sent — all confirmed.
    """
    service = get_drive_service()

    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType, size)"
    ).execute()
    all_files = results.get('files', [])

    # Collect base names that have a .sent marker (fully done)
    already_done = {
        os.path.splitext(f['name'])[0]
        for f in all_files
        if f['name'].lower().endswith('.sent')
    }

    # Return only .mp4s that are NOT yet fully done
    unprocessed = [
        f for f in all_files
        if f['name'].lower().endswith('.mp4')
        and os.path.splitext(f['name'])[0] not in already_done
    ]

    total_videos = len([f for f in all_files if f['name'].lower().endswith('.mp4')])
    print(f"📂 {total_videos} total video(s) | "
          f"{len(already_done)} fully done | "
          f"{len(unprocessed)} to process")

    return unprocessed


# ── Download ──────────────────────────────────────────────────────────────────

def download_video(file_id, file_name, output_dir='./downloads'):
    """
    Download a video file from Google Drive to local disk.
    Shows download progress percentage.
    Returns the local file path.
    """
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, file_name)

    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(output_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request, chunksize=10 * 1024 * 1024)

    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            print(f"  ⬇️  {int(status.progress() * 100)}%", end='\r')
    fh.close()

    print(f"\n✅ Downloaded: {output_path}")
    return output_path


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_srt_to_drive(srt_path, folder_id):
    """
    Upload a .srt file to the Drive folder using OAuth (has storage quota).
    Returns the uploaded file's Drive ID.
    """
    service = get_drive_upload_service()
    file_name = os.path.basename(srt_path)

    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(srt_path, mimetype='text/plain', resumable=True)

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name'
    ).execute()

    print(f"☁️  Uploaded to Drive: {uploaded['name']} (id: {uploaded['id']})")
    return uploaded['id']


def mark_as_sent(base_name, folder_id):
    """
    Upload a tiny .sent marker file to Drive using OAuth.

    Example: base_name='03_26_26' → uploads '03_26_26.sent'

    Only written after ALL steps succeed: transcribe + upload + email.
    """
    service = get_drive_upload_service()
    sent_name = f"{base_name}.sent"

    media = MediaIoBaseUpload(
        io.BytesIO(b"done"),
        mimetype='text/plain',
        resumable=False
    )
    file_metadata = {'name': sent_name, 'parents': [folder_id]}

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name'
    ).execute()

    print(f"📌 Completion marker uploaded: {uploaded['name']}")