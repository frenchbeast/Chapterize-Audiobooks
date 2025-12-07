# Quick Start

## Basic Usage

```bash
# M4B/M4A files (instant - uses existing chapters):
python chapterize_ab.py audiobook.m4b --title "Book Title"

# MP3 files (uses Vosk by default - reliable and tested):
python chapterize_ab.py audiobook.mp3 --title "Book Title"
```

## Optional: Try Alternative Methods

```bash
# Silence detection (fast but no chapter names):
python chapterize_ab.py audiobook.mp3 --detection-method silence --title "Title"

# faster-whisper (may be faster/slower depending on your system):
python chapterize_ab.py audiobook.mp3 --detection-method whisper --title "Title"
# Note: Install first with: pip install faster-whisper

# Force Vosk explicitly:
python chapterize_ab.py audiobook.mp3 --detection-method vosk --title "Title"
```

## Performance Notes

Processing time varies significantly based on:
- Your CPU/GPU hardware
- File size and duration
- Detection method chosen

**Best practice**: Test with a small file first to see which method works best on your system.

For M4B files with embedded chapters, extraction is always instant (~10 seconds).

