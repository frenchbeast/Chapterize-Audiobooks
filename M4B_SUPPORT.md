# M4B/M4A Audiobook Format Support

## Overview

The Chapterize-Audiobooks project now supports **M4B** (MPEG-4 Audio Book) and **M4A** (MPEG-4 Audio) files in addition to MP3 files!

M4B files are commonly used by:
- 📱 Apple Books
- 🎧 Audible
- 📚 Professional audiobook distributors

**Key Advantage:** M4B files often **already contain chapter markers**, which means you can extract chapters **instantly** without ML transcription!

---

## Features

### ✅ What's Supported

1. **Read Existing Chapters** - Extract embedded chapter markers (instant!)
2. **Read M4B Metadata** - Extract title, author, narrator, etc.
3. **Split M4B Files** - Split into individual chapter files
4. **M4A Support** - Same features as M4B
5. **ML Detection Fallback** - If no chapters exist, use Vosk/Whisper
6. **Output Formats** - Split to M4B (no re-encode) or MP3

---

## Quick Start

### Extract Existing Chapters from M4B

```bash
# Method 1: Use main script (will auto-detect M4B and extract chapters)
python chapterize_ab.py audiobook.m4b --title "Book Title"

# Method 2: Use M4B utility directly
python m4b_support.py extract audiobook.m4b

# Method 3: Save chapters to JSON
python m4b_support.py extract audiobook.m4b --output chapters.json
```

### View M4B File Information

```bash
python m4b_support.py info audiobook.m4b
```

Output:
```
=== M4B File Info: audiobook.m4b ===

Metadata:
  album: The Great Gatsby
  album_artist: F. Scott Fitzgerald
  narrator: Jake Gyllenhaal
  genre: Fiction
  date: 2023

Chapters: 25
  1. Chapter 01 - The Beginning
  2. Chapter 02 - Early Life
  3. Chapter 03 - The Party
  ... and 22 more
```

### Split M4B into Chapter Files

```bash
# Split to M4B files (no re-encoding, FAST!)
python m4b_support.py split audiobook.m4b --format m4b

# Split to MP3 files (re-encodes)
python m4b_support.py split audiobook.m4b --format mp3

# Custom output directory
python m4b_support.py split audiobook.m4b --output-dir ~/Audiobooks/Chapters/
```

---

## Workflow Examples

### Scenario 1: M4B with Existing Chapters (INSTANT)

```bash
python chapterize_ab.py audiobook.m4b --title "My Book"

# Output:
# M4B/M4A file detected: audiobook.m4b
# Checking for existing chapter markers...
# SUCCESS! Found 24 embedded chapters
#
# M4B file already has chapters. Options:
#   1. Use existing chapters (fast, recommended)
#   2. Re-detect chapters with ML (slow, may find different breaks)
#
# Choice [1/2] (default: 1): 1
#
# ✓ Using Existing M4B Chapters
# ✓ Audiobook split into 24 files
```

**Time:** Seconds instead of hours! ⚡

### Scenario 2: M4B without Chapters (ML Detection)

```bash
python chapterize_ab.py audiobook.m4b --title "My Book"

# Output:
# M4B/M4A file detected: audiobook.m4b
# Checking for existing chapter markers...
# No embedded chapters found - will use ML detection
#
# [Proceeds with Vosk/Whisper chapter detection]
```

### Scenario 3: Convert M4B to MP3 First

If you need MP3 format for some reason:

```bash
# Convert M4B to MP3
python m4b_support.py convert audiobook.m4b --output audiobook.mp3

# Then process as usual
python chapterize_ab.py audiobook.mp3
```

**Note:** This re-encodes audio which may reduce quality.

---

## M4B Utility Commands

### 1. Extract Chapters

```bash
# Basic extraction
python m4b_support.py extract audiobook.m4b

# Save to JSON file
python m4b_support.py extract audiobook.m4b --output chapters.json

# Example output:
[
  {
    "start": "00:00:00.000",
    "end": "00:15:23.450",
    "chapter_type": "Chapter 01 - Introduction"
  },
  {
    "start": "00:15:23.451",
    "end": "00:32:45.123",
    "chapter_type": "Chapter 02 - The Journey Begins"
  }
]
```

### 2. Get File Information

```bash
python m4b_support.py info audiobook.m4b
```

Shows:
- Metadata (title, author, narrator, etc.)
- Number of chapters
- Chapter titles
- Duration

### 3. Convert to MP3

```bash
# Default output (same name, .mp3 extension)
python m4b_support.py convert audiobook.m4b

# Custom output path
python m4b_support.py convert audiobook.m4b --output /path/to/output.mp3
```

### 4. Split into Chapters

```bash
# Split to M4B files (RECOMMENDED - no re-encoding!)
python m4b_support.py split audiobook.m4b --format m4b

# Split to MP3 files
python m4b_support.py split audiobook.m4b --format mp3

# Custom output directory
python m4b_support.py split audiobook.m4b \
    --format m4b \
    --output-dir ~/Audiobooks/Chapters/
```

**Output Example:**
```
audiobook 01 - Chapter 01 - Introduction.m4b
audiobook 02 - Chapter 02 - The Journey Begins.m4b
audiobook 03 - Chapter 03 - First Encounter.m4b
...
```

---

## Comparison: M4B vs MP3

| Feature | M4B | MP3 |
|---------|-----|-----|
| **Chapter Markers** | ✅ Embedded | ❌ Not supported |
| **Audio Quality** | Better (AAC) | Good |
| **File Size** | Smaller | Larger |
| **Metadata Support** | Excellent | Good |
| **Compatibility** | Apple ecosystem | Universal |
| **Processing Speed** | Instant (if has chapters) | Hours (ML needed) |

---

## Performance Benefits

### With Existing Chapters (M4B):

**Old workflow (without M4B support):**
```
1. Convert M4B to MP3: ~5 minutes
2. Transcribe 12-hour book with Vosk: ~4 hours
3. Split into chapters: ~2 minutes
TOTAL: ~4 hours 7 minutes
```

**New workflow (with M4B support):**
```
1. Extract embedded chapters: ~2 seconds
2. Split into chapters: ~1 minute
TOTAL: ~1 minute!
```

**🎉 Speedup: 247x faster!**

### Without Existing Chapters (M4B):

Same as MP3 workflow - uses ML detection as fallback.

---

## Technical Details

### Supported Formats

- `.m4b` - MPEG-4 Audio Book (primary target)
- `.m4a` - MPEG-4 Audio (same format, different extension)
- `.mp3` - MP3 Audio (original support)

### Dependencies

Already included - uses `ffmpeg`/`ffprobe` which you already have installed!

### Chapter Extraction

The `m4b_support.py` module uses `ffprobe` to extract chapters:

```python
from m4b_support import get_m4b_chapters

chapters = get_m4b_chapters('audiobook.m4b')
# Returns: list of dicts with start, end, chapter_type
```

### Output Formats

When splitting M4B files, you can choose:

1. **M4B output** (recommended)
   - No re-encoding (preserves quality)
   - Fast processing
   - Smaller file sizes
   - Maintains AAC codec

2. **MP3 output**
   - Re-encodes audio (quality loss)
   - Slower processing
   - Universal compatibility
   - Larger file sizes

---

## Common Use Cases

### 1. Quick Chapter Extraction

```bash
# Just want to see what chapters are in an M4B file
python m4b_support.py info audiobook.m4b
```

### 2. Split Existing Audiobook

```bash
# Have an M4B from Audible/Apple Books, want individual chapters
python m4b_support.py split audiobook.m4b --format m4b
```

### 3. Convert Library to MP3

```bash
# Convert all M4B files to MP3
for file in *.m4b; do
    python m4b_support.py convert "$file"
done
```

### 4. Re-detect Chapters

```bash
# M4B has chapters but they're wrong, re-detect with ML
python chapterize_ab.py audiobook.m4b
# Choose option 2 when prompted
```

---

## Troubleshooting

### "No embedded chapters found"

**Cause:** Some M4B files don't have chapter markers.

**Solution:** The script will automatically fall back to ML chapter detection (Vosk/Whisper).

### "ffprobe not found"

**Cause:** ffmpeg/ffprobe not installed.

**Solution:**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# Download from ffmpeg.org
```

### M4B output files won't play

**Cause:** Some players don't support M4B.

**Solution:** Use MP3 output format instead:
```bash
python m4b_support.py split audiobook.m4b --format mp3
```

### Chapters have wrong timestamps

**Cause:** M4B chapters are sometimes inaccurate.

**Solution:** Re-detect chapters with ML:
```bash
python chapterize_ab.py audiobook.m4b
# Choose option 2: Re-detect chapters with ML
```

---

## Best Practices

### 1. Always Check for Existing Chapters First

```bash
python m4b_support.py info audiobook.m4b
```

If chapters exist, extraction is instant!

### 2. Prefer M4B Output Format

When splitting, use M4B output to avoid re-encoding:
```bash
python m4b_support.py split audiobook.m4b --format m4b
```

### 3. Backup Original Files

M4B files from Audible/Apple Books may have DRM. Keep originals safe!

### 4. Use Faster Whisper for Re-detection

If M4B lacks chapters, use faster-whisper instead of Vosk:
```bash
pip install faster-whisper
python chapter_detection_alternatives.py audiobook.m4b --method whisper
```

---

## Integration with Main Script

The main `chapterize_ab.py` script now:

1. ✅ Accepts `.m4b` and `.m4a` files
2. ✅ Auto-detects M4B format
3. ✅ Extracts existing chapters (if present)
4. ✅ Extracts M4B metadata
5. ✅ Gives user choice: use existing or re-detect
6. ✅ Falls back to ML if no chapters found

**Usage:**
```bash
# Works exactly like MP3!
python chapterize_ab.py audiobook.m4b \
    --title "Book Title" \
    --author "Author Name" \
    --narrator "Narrator Name"
```

---

## Examples

### Example 1: Audible Audiobook

```bash
# Download from Audible (if you own it)
# File: the-hobbit.m4b (already has chapters)

python chapterize_ab.py the-hobbit.m4b --write_cue_file

# Output:
# M4B/M4A file detected: the-hobbit.m4b
# Checking for existing chapter markers...
# SUCCESS! Found 19 embedded chapters
#
# Use existing chapters? [1=yes, 2=re-detect]: 1
#
# ✓ Chapters extracted in 2 seconds
# ✓ Split into 19 files
```

### Example 2: Custom M4B (No Chapters)

```bash
# Self-recorded audiobook
# File: my-recording.m4b (no chapters)

python chapterize_ab.py my-recording.m4b

# Output:
# M4B/M4A file detected: my-recording.m4b
# Checking for existing chapter markers...
# No embedded chapters found - will use ML detection
#
# [Proceeds with Vosk/Whisper detection]
```

### Example 3: Batch Processing

```bash
# Process entire M4B library
for book in ~/Audiobooks/*.m4b; do
    echo "Processing: $book"
    python chapterize_ab.py "$book"
done
```

---

## Summary

M4B support brings **instant chapter extraction** for audiobooks that already have chapter markers!

**Benefits:**
- ⚡ **247x faster** for M4B files with chapters
- 📚 **Better metadata** extraction
- 🎯 **No quality loss** when splitting to M4B
- ✅ **Automatic fallback** to ML if no chapters
- 🔧 **Standalone utilities** for M4B manipulation

**Supported:**
- ✅ `.m4b` files (MPEG-4 Audio Book)
- ✅ `.m4a` files (MPEG-4 Audio)
- ✅ `.mp3` files (original support)

**Get Started:**
```bash
python chapterize_ab.py your_audiobook.m4b
```

That's it! The script handles everything automatically. 🎉
