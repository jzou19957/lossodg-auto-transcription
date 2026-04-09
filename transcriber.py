import os
from faster_whisper import WhisperModel


def _should_log_segments():
    """Allow verbose per-segment logs only when explicitly enabled."""
    value = os.environ.get("VERBOSE_TRANSCRIPT_LOGS", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def format_timestamp(seconds):
    """Convert seconds float to SRT timestamp HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def transcribe_to_srt(video_path, output_dir='./output', model_size='medium'):
    """
    Transcribe a video file using Whisper and save as .srt.
    Output filename matches input with .srt extension.
    """
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(video_path))[0]
    srt_path = os.path.join(output_dir, f"{base_name}.srt")

    print(f"🤖 Loading Whisper model ({model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"🎙️  Transcribing: {os.path.basename(video_path)}")
    segments, info = model.transcribe(
        video_path,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )

    print(f"   Language detected: {info.language} ({info.language_probability:.0%} confidence)")
    verbose_segments = _should_log_segments()
    if verbose_segments:
        print("   Verbose transcript logging enabled")

    segment_count = 0
    with open(srt_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, 1):
            start = format_timestamp(segment.start)
            end = format_timestamp(segment.end)
            text = segment.text.strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
            segment_count += 1
            if verbose_segments:
                print(f"   [{start}] {text[:70]}{'...' if len(text) > 70 else ''}")

    print(f"✅ SRT saved: {srt_path} ({segment_count} segments)")
    return srt_path, base_name
