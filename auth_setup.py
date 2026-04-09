"""
auth_setup.py — Run this ONCE locally to authenticate with Google.

This opens a browser window for you to log in with your Google account.
It saves token files which you then encode and store as a GitHub Secret
(GOOGLE_TOKEN_B64) so GitHub Actions can use it.

Usage:
    python auth_setup.py

Requirements:
    - credentials.json must be in this folder (from Google Cloud Console)
    - pip install google-auth-oauthlib google-auth-httplib2
"""

import os
import pickle
import base64
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/gmail.send'
]


def main():
    if not os.path.exists('credentials.json'):
        print("❌ credentials.json not found!")
        print("   Download it from Google Cloud Console:")
        print("   https://console.cloud.google.com/ → APIs & Services → Credentials")
        print("   → Create OAuth 2.0 Client ID (Desktop App) → Download JSON → rename to credentials.json")
        return

    creds = None

    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print("⚠️  Existing local OAuth token is expired or revoked.")
                print("   Starting a fresh Google sign-in to generate a new token...")
                creds = None
        else:
            creds = None

        if creds is None:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(
                port=0,
                access_type='offline',
                prompt='consent'
            )

        with open('token.pickle', 'wb') as f:
            pickle.dump(creds, f)

        with open('token.json', 'w', encoding='utf-8') as f:
            f.write(creds.to_json())

    print("✅ token.pickle saved!")
    print("✅ token.json saved!")
    print()

    # Encode the JSON token for GitHub Secrets.
    with open('token.json', 'r', encoding='utf-8') as f:
        encoded = base64.b64encode(f.read().encode('utf-8')).decode()

    print("=" * 60)
    print("📋 NEXT STEP — Add this as a GitHub Secret:")
    print("   Name : GOOGLE_TOKEN_B64")
    print("   Value: (saved to token_b64.txt in this folder)")
    print("=" * 60)

    with open('token_b64.txt', 'w') as f:
        f.write(encoded)

    print()
    print("✅ token_b64.txt created. Copy its contents into GitHub Secrets.")
    print("⚠️  Do NOT commit token.pickle or token_b64.txt to GitHub!")


if __name__ == '__main__':
    main()
