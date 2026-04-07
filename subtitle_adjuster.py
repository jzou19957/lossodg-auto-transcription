import re


TIMESTAMP_PATTERN = re.compile(
    r'^(?P<start>\d{2}:\d{2}:\d{2},\d{3}) --> (?P<end>\d{2}:\d{2}:\d{2},\d{3})$'
)


def parse_timestamp(timestamp):
    """Convert an SRT timestamp string to milliseconds."""
    hours, minutes, seconds_ms = timestamp.split(':')
    seconds, milliseconds = seconds_ms.split(',')
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(milliseconds)
    )


def format_timestamp(milliseconds):
    """Convert milliseconds to an SRT timestamp string."""
    milliseconds = max(0, int(milliseconds))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def shift_srt_to_zero(srt_path):
    """
    Shift all subtitle timestamps so the first non-blank cue starts at 00:00:00,000.

    Returns a tuple of:
      - applied shift in milliseconds
      - first cue text used for alignment

    Returns (0, "") if no adjustment is needed.
    """
    with open(srt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    first_start_ms = None
    first_text = ''
    adjusted_lines = []

    for index, line in enumerate(lines):
        stripped = line.strip()
        match = TIMESTAMP_PATTERN.match(stripped)

        if first_start_ms is None and match:
            text_line = ''
            look_ahead = index + 1
            while look_ahead < len(lines):
                candidate = lines[look_ahead].strip()
                if candidate:
                    text_line = candidate
                    break
                look_ahead += 1

            if text_line:
                first_start_ms = parse_timestamp(match.group('start'))
                first_text = text_line

        adjusted_lines.append(line)

    if first_start_ms in (None, 0):
        return 0, first_text

    for index, line in enumerate(adjusted_lines):
        match = TIMESTAMP_PATTERN.match(line.strip())
        if not match:
            continue

        shifted_start = format_timestamp(parse_timestamp(match.group('start')) - first_start_ms)
        shifted_end = format_timestamp(parse_timestamp(match.group('end')) - first_start_ms)
        adjusted_lines[index] = f"{shifted_start} --> {shifted_end}\n"

    with open(srt_path, 'w', encoding='utf-8') as f:
        f.writelines(adjusted_lines)

    return first_start_ms, first_text
