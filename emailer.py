import os
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from downloader import get_gmail_service


def send_srt_email(srt_path, video_name, recipient_email):
    """Send the .srt file as an email attachment via Gmail API."""
    service = get_gmail_service()

    msg = MIMEMultipart()
    msg['To'] = recipient_email
    msg['Subject'] = f"✅ Subtitles ready: {video_name}"

    body = f"""Hi,

Your subtitle file for "{video_name}" has been generated and is attached.

A copy has also been saved back to your Google Drive folder alongside the original video.

File: {os.path.basename(srt_path)}
Model: Whisper medium

---
Video-to-Subtitles Bot (GitHub Actions)
"""
    msg.attach(MIMEText(body, 'plain'))

    with open(srt_path, 'rb') as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename="{os.path.basename(srt_path)}"'
        )
        msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()
    print(f"📧 Email sent → {recipient_email}")
