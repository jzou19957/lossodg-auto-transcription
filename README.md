# 🎬 Video-to-Subtitles Bot

Automatically scans a Google Drive folder for `.mp4` videos, transcribes them with Whisper, saves the `.srt` back to Drive, and emails it to you.

**Runs every 5 minutes via GitHub Actions — Mon–Fri, 10am–5pm Central.**

---

## 🔁 How It Works

```
GitHub Actions triggers every 5 min (Mon–Fri 10am–5pm CT)
        ↓
Scans your Google Drive folder for .mp4 files
        ↓
Skips any video that already has a matching .srt (already processed)
        ↓
Downloads unprocessed video → transcribes with Whisper medium
        ↓
Uploads .srt back to same Drive folder (backup copy)
        ↓
Emails .srt to jiajun@livebash.com
```

---

## 🚀 Setup Guide

### Step 1 — Google Cloud Console (one-time, ~5 min)

1. Go to https://console.cloud.google.com/
2. Create a new project
3. Enable these APIs:
   - **Google Drive API**
   - **Gmail API**
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → OAuth 2.0 Client ID → Desktop App**
6. Download the JSON → rename to `credentials.json` → place in this folder

### Step 2 — Authenticate Locally (one-time)

```bash
pip install -r requirements.txt
python auth_setup.py
```

A browser window opens → log in with your Google account → authorize both Drive and Gmail.

This creates `token.pickle` and `token_b64.txt`.

### Step 3 — Add GitHub Secrets

In your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret Name | Value |
|---|---|
| `GOOGLE_TOKEN_B64` | Contents of `token_b64.txt` |
| `DRIVE_FOLDER_ID` | Your Google Drive folder ID (see below) |
| `RECIPIENT_EMAIL` | `jiajun@livebash.com` |

**Finding your Drive Folder ID:**
Open the folder in Google Drive → look at the URL:
```
https://drive.google.com/drive/folders/THIS_PART_IS_THE_FOLDER_ID
```

### Step 4 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/video-to-subtitles.git
git push -u origin main
```

GitHub Actions will start running automatically on schedule.

---

## 🧪 Testing Manually

In your GitHub repo → **Actions → Video to Subtitles → Run workflow**

This lets you trigger a run instantly without waiting for the schedule.

---

## 📁 File Structure

```
video-to-subtitles/
├── main.py                        ← Entry point (called by GitHub Actions)
├── downloader.py                  ← Drive download/upload + auth
├── transcriber.py                 ← Whisper transcription → .srt
├── emailer.py                     ← Gmail send logic
├── auth_setup.py                  ← Run once locally to get token
├── requirements.txt
├── .gitignore
├── .github/
│   └── workflows/
│       └── transcribe.yml         ← GitHub Actions schedule
└── README.md
```

---

## ⚠️ Important Security Notes

- **Never commit** `credentials.json`, `token.pickle`, or `token_b64.txt`
- These are already in `.gitignore` for safety
- The `GOOGLE_TOKEN_B64` secret expires after ~6 months — re-run `auth_setup.py` to refresh

---

## 🕐 Schedule

| Day | Hours (Central Time) | Behavior |
|-----|----------------------|----------|
| Mon–Fri | 10:00am – 5:00pm | Scans every 5 min |
| Mon–Fri | Outside hours | Exits immediately |
| Sat–Sun | Any | Exits immediately |

> Drop a new `.mp4` into your Drive folder any time — it'll be picked up during the next active window.
