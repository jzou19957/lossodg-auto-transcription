import os
import io
import json
import base64
import pickle
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/gmail.send'
]


def get_credentials():
    """
    Build Google credentials from environment variable (for GitHub Actions)
    or from token.pickle (for local dev).
    """
    creds = None

    # GitHub Actions: credentials stored as base64 env var
    token_b64 = os.environ.get('GOOGLE_TOKEN_B64')
    if token_b64:
        token_bytes = base64.b64decode(token_b64)
        creds = pickle.loads(token_bytes)

    # Local dev: use token.pickle file
    elif os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        raise RuntimeError(
            "No valid credentials found.\n"
            "Run auth_setup.py locally first to generate token.pickle,\n"
            "then encode it as GOOGLE_TOKEN_B64 in GitHub Secrets."
        )

    return creds


def get_drive_service():
    return build('drive', 'v3', credentials=get_credentials())


def get_gmail_service():
    return build('gmail', 'v1', credentials=get_credentials())


def list_unprocessed_videos(folder_id):
    """
    List all .mp4 files in the Drive folder that don't already
    have a matching .srt file (same base name).
    """
    service = get_drive_service()

    # Get all files in the folder
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType, size)"
    ).execute()
    files = results.get('files', [])

    # Build a set of base names that already have .srt files
    existing_srts = {
        os.path.splitext(f['name'])[0]
        for f in files
        if f['name'].lower().endswith('.srt')
    }

    # Return mp4 files that don't have a matching .srt yet
    unprocessed = [
        f for f in files
        if f['name'].lower().endswith('.mp4')
        and os.path.splitext(f['name'])[0] not in existing_srts
    ]

    print(f"📂 Found {len(files)} total files, {len(unprocessed)} unprocessed video(s)")
    return unprocessed


def download_video(file_id, file_name, output_dir='./downloads'):
    """Download a video file from Google Drive."""
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


def upload_srt_to_drive(srt_path, folder_id):
    """Upload the .srt file back to the same Drive folder."""
    service = get_drive_service()
    file_name = os.path.basename(srt_path)

    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(srt_path, mimetype='text/plain', resumable=True)
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name'
    ).execute()

    print(f"☁️  Uploaded to Drive: {uploaded['name']} (id: {uploaded['id']})")
    return uploaded['id']
