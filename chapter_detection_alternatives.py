#!/usr/bin/env python3
"""
Alternative chapter detection methods for chapterize_ab.py

This module provides more efficient alternatives to the default Vosk transcription:
1. Silence detection (fastest, no transcription)
2. faster-whisper (best balance of speed/accuracy)
3. Hybrid approach (silence detection + selective transcription)

Usage:
    python chapter_detection_alternatives.py /path/to/audiobook.mp3 --method whisper
"""

from pathlib import Path
from typing import Optional
import argparse

# Method 1: Silence Detection
def detect_by_silence(audiobook_path: Path,
                     min_silence_len: int = 2000,
                     silence_thresh: int = -40) -> list[dict]:
    """
    Detect chapters by finding long pauses (FASTEST method).

    No transcription needed - just analyzes audio amplitude.
    Typically completes in seconds instead of hours.

    :param audiobook_path: Path to audiobook MP3
    :param min_silence_len: Minimum silence duration in ms (default 2000ms)
    :param silence_thresh: Silence threshold in dBFS (default -40)
    :return: List of chapter dictionaries
    """
    try:
        from pydub import AudioSegment
        from pydub.silence import detect_nonsilent
    except ImportError:
        raise ImportError(
            "pydub is required for silence detection. "
            "Install with: pip install pydub"
        )

    print(f"[Silence Detection] Loading audio: {audiobook_path.name}")
    audio = AudioSegment.from_mp3(audiobook_path)

    print(f"[Silence Detection] Analyzing {len(audio) / 1000 / 60:.1f} minutes of audio...")

    # Detect non-silent ranges (chapters are between silences)
    nonsilent_ranges = detect_nonsilent(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=silence_thresh,
        seek_step=100  # Check every 100ms
    )

    print(f"[Silence Detection] Found {len(nonsilent_ranges)} potential chapters")

    # Convert to chapter format
    chapters = []
    for i, (start_ms, end_ms) in enumerate(nonsilent_ranges, start=1):
        chapters.append({
            'start': _ms_to_timestamp(start_ms),
            'end': _ms_to_timestamp(end_ms),
            'chapter_type': f'Chapter {i:02d}'
        })

    # Remove the end from the last chapter
    if chapters:
        chapters[-1].pop('end', None)

    return chapters


# Method 2: faster-whisper (Recommended)
def detect_by_whisper(audiobook_path: Path,
                     model_size: str = "base",
                     device: str = "cpu",
                     language: str = "en") -> list[dict]:
    """
    Detect chapters using faster-whisper (RECOMMENDED method).

    Up to 10x faster than Vosk, highly accurate.
    Includes automatic voice activity detection to skip silence.

    :param audiobook_path: Path to audiobook MP3
    :param model_size: Model size - tiny, base, small, medium, large-v2
    :param device: "cpu" or "cuda" for GPU acceleration
    :param language: Language code (en, es, fr, de, etc.)
    :return: List of chapter dictionaries
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError(
            "faster-whisper is required. "
            "Install with: pip install faster-whisper"
        )

    print(f"[faster-whisper] Loading model: {model_size}")
    model = WhisperModel(
        model_size,
        device=device,
        compute_type="int8"  # Faster inference
    )

    print(f"[faster-whisper] Transcribing: {audiobook_path.name}")
    print("This may take a while for long audiobooks...")

    segments, info = model.transcribe(
        str(audiobook_path),
        language=language,
        beam_size=5,
        vad_filter=True,  # Skip silence automatically!
        vad_parameters=dict(min_silence_duration_ms=500)
    )

    print(f"[faster-whisper] Detected language: {info.language} "
          f"(probability: {info.language_probability:.2f})")

    # Extract chapter markers
    chapters = []
    chapter_keywords = ['prologue', 'chapter', 'epilogue']
    excluded_phrases = [
        'chapter and verse', 'chapters', 'this chapter', 'that chapter',
        'chapter of', 'in chapter', 'and chapter', 'next chapter'
    ]

    counter = 1
    for segment in segments:
        text = segment.text.strip()
        text_lower = text.lower()

        # Check if this segment mentions a chapter marker
        if any(keyword in text_lower for keyword in chapter_keywords):
            # Exclude false positives
            if any(excluded in text_lower for excluded in excluded_phrases):
                continue

            # Determine chapter type
            if 'prologue' in text_lower:
                chapter_type = 'Prologue'
            elif 'epilogue' in text_lower:
                chapter_type = 'Epilogue'
            elif 'chapter' in text_lower:
                chapter_type = f'Chapter {counter:02d}'
                counter += 1
            else:
                chapter_type = text.title()

            chapters.append({
                'start': _seconds_to_timestamp(segment.start),
                'chapter_type': chapter_type
            })

    # Add end times (start of next chapter - 1 second)
    for i in range(len(chapters) - 1):
        next_start = chapters[i + 1]['start']
        chapters[i]['end'] = _subtract_one_second(next_start)

    print(f"[faster-whisper] Found {len(chapters)} chapters")
    return chapters


# Method 3: Hybrid Approach
def detect_hybrid(audiobook_path: Path,
                 model_size: str = "tiny",
                 silence_len: int = 1500,
                 silence_thresh: int = -40) -> list[dict]:
    """
    Hybrid approach: Silence detection + selective transcription (SMARTEST method).

    1. Find long silences (potential chapter boundaries)
    2. Transcribe only 30 seconds around each silence
    3. Confirm if it's a chapter marker

    Only transcribes ~5-10% of audiobook - much faster!

    :param audiobook_path: Path to audiobook MP3
    :param model_size: Whisper model size (use tiny for speed)
    :param silence_len: Minimum silence length in ms
    :param silence_thresh: Silence threshold in dBFS
    :return: List of chapter dictionaries
    """
    try:
        from pydub import AudioSegment
        from pydub.silence import detect_silence
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ImportError(
            f"Missing dependency: {e}\n"
            "Install with: pip install pydub faster-whisper"
        )

    print(f"[Hybrid] Step 1/3: Detecting silence...")
    audio = AudioSegment.from_mp3(audiobook_path)

    silences = detect_silence(
        audio,
        min_silence_len=silence_len,
        silence_thresh=silence_thresh,
        seek_step=100
    )

    print(f"[Hybrid] Found {len(silences)} potential chapter boundaries")

    if not silences:
        print("[Hybrid] No silences found - falling back to full transcription")
        return detect_by_whisper(audiobook_path, model_size="tiny")

    print(f"[Hybrid] Step 2/3: Loading Whisper model ({model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print("[Hybrid] Step 3/3: Selectively transcribing around silence points...")

    chapters = []
    chapter_keywords = ['prologue', 'chapter', 'epilogue']
    temp_segment = Path("/tmp/temp_segment.mp3")

    for idx, (silence_start, silence_end) in enumerate(silences):
        # Extract 30 seconds around silence (15s before, 15s after)
        start = max(0, silence_start - 15000)
        end = min(len(audio), silence_end + 15000)

        segment = audio[start:end]
        segment.export(temp_segment, format="mp3")

        # Transcribe this small segment
        segments, _ = model.transcribe(str(temp_segment), language="en")

        # Check if it contains a chapter marker
        found_chapter = False
        for seg in segments:
            text = seg.text.lower().strip()
            if any(keyword in text for keyword in chapter_keywords):
                # Calculate absolute timestamp
                absolute_time_ms = start + (seg.start * 1000)

                chapters.append({
                    'start': _ms_to_timestamp(int(absolute_time_ms)),
                    'chapter_type': seg.text.strip().title()
                })
                found_chapter = True
                break

        if found_chapter:
            print(f"  ✓ Found chapter at {_ms_to_timestamp(silence_start)}")

    # Clean up
    if temp_segment.exists():
        temp_segment.unlink()

    # Add end times
    for i in range(len(chapters) - 1):
        chapters[i]['end'] = _subtract_one_second(chapters[i + 1]['start'])

    print(f"[Hybrid] Found {len(chapters)} chapters")
    return chapters


# Utility functions
def _ms_to_timestamp(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS.mmm format."""
    seconds = ms // 1000
    milliseconds = ms % 1000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def _seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm format."""
    return _ms_to_timestamp(int(seconds * 1000))


def _subtract_one_second(timestamp: str) -> str:
    """Subtract one second from timestamp for end markers."""
    parts = timestamp.split(':')
    last_part = parts[-1]
    secs, ms = last_part.split('.')

    total_seconds = (
        int(parts[0]) * 3600 +
        int(parts[1]) * 60 +
        int(secs) - 1
    )

    if total_seconds < 0:
        total_seconds = 0

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms}"


# CLI Interface
def main():
    """Command-line interface for alternative chapter detection methods."""
    parser = argparse.ArgumentParser(
        description="Alternative chapter detection methods for audiobooks"
    )
    parser.add_argument('audiobook', type=Path, help='Path to audiobook MP3 file')
    parser.add_argument(
        '--method',
        choices=['silence', 'whisper', 'hybrid'],
        default='whisper',
        help='Detection method (default: whisper)'
    )
    parser.add_argument(
        '--model-size',
        default='base',
        choices=['tiny', 'base', 'small', 'medium', 'large-v2'],
        help='Whisper model size (default: base)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file for chapter list (default: print to console)'
    )

    args = parser.parse_args()

    if not args.audiobook.exists():
        print(f"Error: File not found: {args.audiobook}")
        return 1

    # Detect chapters using selected method
    if args.method == 'silence':
        chapters = detect_by_silence(args.audiobook)
    elif args.method == 'whisper':
        chapters = detect_by_whisper(args.audiobook, model_size=args.model_size)
    elif args.method == 'hybrid':
        chapters = detect_hybrid(args.audiobook, model_size=args.model_size)

    # Output results
    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(chapters, f, indent=2)
        print(f"\nChapter list saved to: {args.output}")
    else:
        print("\n=== Detected Chapters ===")
        for i, chapter in enumerate(chapters, 1):
            end_str = f" -> {chapter['end']}" if 'end' in chapter else ""
            print(f"{i}. {chapter['chapter_type']}: {chapter['start']}{end_str}")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
