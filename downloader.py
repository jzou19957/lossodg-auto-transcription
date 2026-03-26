import os
import io
import json
import base64
import pickle
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaIoBaseUpload

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/gmail.send'
]

LOG_FILE_NAME = 'processed_log.txt'


def get_credentials():
    creds = None
    token_b64 = os.environ.get('GOOGLE_TOKEN_B64')
    if token_b64:
        token_bytes = base64.b64decode(token_b64)
        creds = pickle.loads(token_bytes)
    elif os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)
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


def list_all_videos(folder_id):
    """Return all .mp4 files in the Drive folder."""
    service = get_drive_service()
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType, size)"
    ).execute()
    files = results.get('files', [])
    videos = [f for f in files if f['name'].lower().endswith('.mp4')]
    return videos


def load_processed_log(folder_id):
    """
    Load processed_log.txt from Drive.
    Returns a set of video filenames that were fully completed
    (transcribed + uploaded + emailed).
    Creates an empty log if none exists yet.
    """
    service = get_drive_service()
    results = service.files().list(
        q=f"'{folder_id}' in parents and name='{LOG_FILE_NAME}' and trashed=false",
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])

    if not files:
        print(f"📋 No {LOG_FILE_NAME} found — starting fresh log")
        return set()

    file_id = files[0]['id']
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    content = fh.getvalue().decode('utf-8')
    log = set(line.strip() for line in content.splitlines() if line.strip())
    return log


def save_processed_log(processed_log, folder_id):
    """
    Save the updated processed_log.txt back to Drive.
    Overwrites the existing file or creates a new one.
    """
    service = get_drive_service()
    content = '\n'.join(sorted(processed_log)).encode('utf-8')
    fh = io.BytesIO(content)
    media = MediaIoBaseUpload(fh, mimetype='text/plain', resumable=False)

    # Check if log file already exists
    results = service.files().list(
        q=f"'{folder_id}' in parents and name='{LOG_FILE_NAME}' and trashed=false",
        fields="files(id)"
    ).execute()
    existing = results.get('files', [])

    if existing:
        # Update existing file
        service.files().update(
            fileId=existing[0]['id'],
            media_body=media
        ).execute()
    else:
        # Create new file
        file_metadata = {'name': LOG_FILE_NAME, 'parents': [folder_id]}
        service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

    print(f"💾 processed_log.txt saved ({len(processed_log)} entries)")


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
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(srt_path, mimetype='text/plain', resumable=True)
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name'
    ).execute()
    print(f"☁️  Uploaded to Drive: {uploaded['name']} (id: {uploaded['id']})")
    return uploaded['id']
