# Quick Start

## Basic Usage

```bash
# M4B/M4A files (instant - uses existing chapters):
python chapterize_ab.py audiobook.m4b --title "Book Title"

# MP3 files (auto-detects best method):
python chapterize_ab.py audiobook.mp3 --title "Book Title"
```

## Make It 5-10x Faster (Recommended)

```bash
# Install faster detection (one-time):
pip install faster-whisper

# Use the script normally - it auto-detects faster-whisper!
python chapterize_ab.py audiobook.mp3 --title "Book Title"
```

**That's it!** The script automatically uses the fastest method available.

## Manual Method Selection (Optional)

```bash
# Force a specific method:
python chapterize_ab.py audiobook.mp3 --detection-method whisper  # 5-10x faster
python chapterize_ab.py audiobook.mp3 --detection-method hybrid   # 10-15x faster
python chapterize_ab.py audiobook.mp3 --detection-method silence  # 100x faster (no names)
python chapterize_ab.py audiobook.mp3 --detection-method vosk     # Default (slow)
```

## Time Comparison (12-hour audiobook)

- **M4B with chapters**: ~10 seconds ⚡
- **MP3 + faster-whisper**: ~38 minutes 🚀
- **MP3 + Vosk (default)**: ~4 hours 23 minutes 🐌

Install faster-whisper to save hours!
