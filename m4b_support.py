#!/usr/bin/env python3
"""
M4B (MPEG-4 Audio Book) file support for chapterize_ab.py

This module provides utilities for working with M4B audiobook files:
- Extract existing chapter markers from M4B files
- Convert M4B to MP3 for processing
- Split M4B files into chapters
- Create M4B files with chapter markers

M4B files often already contain chapter information, so this module
can extract those chapters directly without ML transcription.
"""

from pathlib import Path
from typing import Optional
import subprocess
import json
import re
from datetime import timedelta


def has_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    from shutil import which
    return which('ffmpeg') is not None


def get_m4b_chapters(m4b_path: Path, ffmpeg: str = 'ffmpeg') -> Optional[list[dict]]:
    """
    Extract existing chapter markers from M4B file.

    M4B files often contain embedded chapter information. This function
    extracts those chapters directly without needing ML transcription.

    :param m4b_path: Path to M4B audiobook file
    :param ffmpeg: Path to ffmpeg executable
    :return: List of chapter dictionaries, or None if no chapters found
    """
    if not m4b_path.exists():
        raise FileNotFoundError(f"M4B file not found: {m4b_path}")

    print(f"[M4B] Extracting chapters from: {m4b_path.name}")

    try:
        # Use ffprobe to get chapter information
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_chapters',
                str(m4b_path)
            ],
            capture_output=True,
            text=True,
            check=True
        )

        data = json.loads(result.stdout)

        if 'chapters' not in data or not data['chapters']:
            print("[M4B] No embedded chapters found")
            return None

        chapters = []
        for i, chapter in enumerate(data['chapters'], start=1):
            # Extract chapter metadata
            start_time = float(chapter.get('start_time', 0))
            end_time = float(chapter.get('end_time', 0))

            # Get chapter title from tags
            tags = chapter.get('tags', {})
            title = tags.get('title', f'Chapter {i:02d}')

            chapters.append({
                'start': _seconds_to_timestamp(start_time),
                'end': _seconds_to_timestamp(end_time),
                'chapter_type': title
            })

        print(f"[M4B] Found {len(chapters)} embedded chapters")
        return chapters

    except subprocess.CalledProcessError as e:
        print(f"[M4B] Error extracting chapters: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[M4B] Error parsing chapter data: {e}")
        return None
    except FileNotFoundError:
        print("[M4B] ffprobe not found. Install ffmpeg to extract chapters.")
        return None


def get_m4b_metadata(m4b_path: Path) -> dict:
    """
    Extract metadata from M4B file.

    :param m4b_path: Path to M4B file
    :return: Dictionary of metadata
    """
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                str(m4b_path)
            ],
            capture_output=True,
            text=True,
            check=True
        )

        data = json.loads(result.stdout)
        format_data = data.get('format', {})
        tags = format_data.get('tags', {})

        # Map M4B tags to our metadata format
        metadata = {}

        if title := tags.get('title'):
            metadata['album'] = title
        if artist := tags.get('artist'):
            metadata['album_artist'] = artist
        if album_artist := tags.get('album_artist'):
            metadata['album_artist'] = album_artist
        if genre := tags.get('genre'):
            metadata['genre'] = genre
        if date := tags.get('date'):
            metadata['date'] = date
        if comment := tags.get('comment'):
            metadata['comment'] = comment
        if description := tags.get('description'):
            metadata['description'] = description
        if composer := tags.get('composer'):
            metadata['narrator'] = composer

        return metadata

    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"[M4B] Could not extract metadata: {e}")
        return {}


def convert_m4b_to_mp3(m4b_path: Path,
                       output_path: Optional[Path] = None,
                       ffmpeg: str = 'ffmpeg') -> Path:
    """
    Convert M4B file to MP3 for processing.

    This is useful if you want to use the existing MP3-based chapter detection.
    Note: This re-encodes the audio, which may reduce quality.

    :param m4b_path: Path to M4B file
    :param output_path: Optional output path (default: same name with .mp3)
    :param ffmpeg: Path to ffmpeg executable
    :return: Path to converted MP3 file
    """
    if output_path is None:
        output_path = m4b_path.with_suffix('.mp3')

    print(f"[M4B] Converting to MP3: {m4b_path.name}")
    print("[M4B] Note: This re-encodes audio and may reduce quality")

    try:
        subprocess.run(
            [
                ffmpeg,
                '-i', str(m4b_path),
                '-vn',  # No video
                '-acodec', 'libmp3lame',
                '-b:a', '128k',  # 128 kbps MP3
                '-y',  # Overwrite
                str(output_path)
            ],
            check=True,
            capture_output=True
        )

        print(f"[M4B] Converted to: {output_path}")
        return output_path

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to convert M4B to MP3: {e}")


def split_m4b_by_chapters(m4b_path: Path,
                          chapters: list[dict],
                          output_dir: Optional[Path] = None,
                          output_format: str = 'm4b',
                          ffmpeg: str = 'ffmpeg') -> list[Path]:
    """
    Split M4B file into separate chapter files.

    Can output as M4B (no re-encoding, fast) or MP3 (re-encoded).

    :param m4b_path: Path to M4B file
    :param chapters: List of chapter dictionaries with start/end times
    :param output_dir: Output directory (default: same as input)
    :param output_format: 'm4b' (no re-encode) or 'mp3' (re-encode)
    :param ffmpeg: Path to ffmpeg executable
    :return: List of paths to created chapter files
    """
    if output_dir is None:
        output_dir = m4b_path.parent

    output_dir.mkdir(parents=True, exist_ok=True)

    file_stem = m4b_path.stem
    output_files = []

    print(f"[M4B] Splitting into {len(chapters)} chapters ({output_format} format)")

    for i, chapter in enumerate(chapters, start=1):
        chapter_num = f'{i:02d}'
        chapter_title = chapter.get('chapter_type', f'Chapter {chapter_num}')

        # Clean title for filename
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', chapter_title)

        if output_format == 'm4b':
            output_file = output_dir / f"{file_stem} {chapter_num} - {safe_title}.m4b"
            codec_args = ['-c', 'copy']  # No re-encoding (fast!)
        else:
            output_file = output_dir / f"{file_stem} {chapter_num} - {safe_title}.mp3"
            codec_args = ['-acodec', 'libmp3lame', '-b:a', '128k']

        # Build ffmpeg command
        cmd = [
            ffmpeg,
            '-i', str(m4b_path),
            '-ss', chapter['start']
        ]

        if 'end' in chapter:
            cmd.extend(['-to', chapter['end']])

        cmd.extend([
            '-vn',  # No video
            *codec_args,
            '-metadata', f"title={chapter_title}",
            '-metadata', f"track={i}/{len(chapters)}",
            '-y',
            str(output_file)
        ])

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            output_files.append(output_file)
            print(f"  ✓ Created: {output_file.name}")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to create: {output_file.name}")
            print(f"    Error: {e}")

    print(f"[M4B] Created {len(output_files)} chapter files")
    return output_files


def create_m4b_with_chapters(input_audio: Path,
                             chapters: list[dict],
                             output_path: Path,
                             metadata: Optional[dict] = None,
                             ffmpeg: str = 'ffmpeg') -> Path:
    """
    Create M4B file with embedded chapter markers.

    This creates a single M4B file with chapter markers embedded,
    similar to professionally produced audiobooks.

    :param input_audio: Path to input audio file (MP3, M4A, M4B, etc.)
    :param chapters: List of chapter dictionaries
    :param output_path: Output M4B file path
    :param metadata: Optional metadata dictionary
    :param ffmpeg: Path to ffmpeg executable
    :return: Path to created M4B file
    """
    print(f"[M4B] Creating M4B with embedded chapters: {output_path.name}")

    # Create metadata file for chapters
    metadata_content = ";FFMETADATA1\n"

    # Add global metadata
    if metadata:
        for key, value in metadata.items():
            metadata_content += f"{key}={value}\n"

    # Add chapter markers
    for chapter in chapters:
        start_ms = _timestamp_to_ms(chapter['start'])
        end_ms = _timestamp_to_ms(chapter.get('end', chapter['start']))

        metadata_content += f"""
[CHAPTER]
TIMEBASE=1/1000
START={start_ms}
END={end_ms}
title={chapter.get('chapter_type', 'Chapter')}
"""

    # Write metadata to temporary file
    metadata_file = output_path.parent / 'ffmetadata.txt'
    try:
        with open(metadata_file, 'w', encoding='utf-8') as f:
            f.write(metadata_content)

        # Create M4B with chapters
        cmd = [
            ffmpeg,
            '-i', str(input_audio),
            '-i', str(metadata_file),
            '-map_metadata', '1',
            '-c', 'copy',
            '-y',
            str(output_path)
        ]

        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[M4B] Created: {output_path}")

        return output_path

    finally:
        # Clean up metadata file
        if metadata_file.exists():
            metadata_file.unlink()


# Utility functions

def _seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm format."""
    td = timedelta(seconds=seconds)
    hours = int(td.total_seconds() // 3600)
    minutes = int((td.total_seconds() % 3600) // 60)
    secs = int(td.total_seconds() % 60)
    ms = int((td.total_seconds() % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def _timestamp_to_ms(timestamp: str) -> int:
    """Convert HH:MM:SS.mmm timestamp to milliseconds."""
    parts = timestamp.split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    secs_parts = parts[2].split('.')
    seconds = int(secs_parts[0])
    ms = int(secs_parts[1]) if len(secs_parts) > 1 else 0

    total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + ms
    return total_ms


# CLI interface

def main():
    """Command-line interface for M4B utilities."""
    import argparse

    parser = argparse.ArgumentParser(
        description="M4B audiobook file utilities"
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Extract chapters command
    extract_parser = subparsers.add_parser(
        'extract',
        help='Extract existing chapters from M4B file'
    )
    extract_parser.add_argument('m4b_file', type=Path, help='M4B file to process')
    extract_parser.add_argument(
        '--output', '-o',
        type=Path,
        help='Output file for chapter list (JSON)'
    )

    # Convert command
    convert_parser = subparsers.add_parser(
        'convert',
        help='Convert M4B to MP3'
    )
    convert_parser.add_argument('m4b_file', type=Path, help='M4B file to convert')
    convert_parser.add_argument(
        '--output', '-o',
        type=Path,
        help='Output MP3 file path'
    )

    # Split command
    split_parser = subparsers.add_parser(
        'split',
        help='Split M4B into chapter files'
    )
    split_parser.add_argument('m4b_file', type=Path, help='M4B file to split')
    split_parser.add_argument(
        '--format', '-f',
        choices=['m4b', 'mp3'],
        default='m4b',
        help='Output format (default: m4b - no re-encoding)'
    )
    split_parser.add_argument(
        '--output-dir', '-d',
        type=Path,
        help='Output directory (default: same as input)'
    )

    # Info command
    info_parser = subparsers.add_parser(
        'info',
        help='Display M4B file information'
    )
    info_parser.add_argument('m4b_file', type=Path, help='M4B file to inspect')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Verify file exists for all commands
    if hasattr(args, 'm4b_file'):
        if not args.m4b_file.exists():
            print("\n" + "="*60)
            print("ERROR: File not found")
            print("="*60)
            print(f"\nFile: {args.m4b_file}")
            print("\nPlease check:")
            print("  - The file path is correct")
            print("  - The file exists at the specified location")
            print("  - You have permission to access the file")
            print("\nSupported formats: .m4b, .m4a")
            print("="*60 + "\n")
            return 1

    # Execute command
    if args.command == 'extract':
        chapters = get_m4b_chapters(args.m4b_file)
        if chapters:
            if args.output:
                import json
                with open(args.output, 'w') as f:
                    json.dump(chapters, f, indent=2)
                print(f"Chapters saved to: {args.output}")
            else:
                print("\n=== Extracted Chapters ===")
                for i, chapter in enumerate(chapters, 1):
                    print(f"{i}. {chapter['chapter_type']}: {chapter['start']} -> {chapter['end']}")
        else:
            print("No chapters found in M4B file")
            return 1

    elif args.command == 'convert':
        convert_m4b_to_mp3(args.m4b_file, args.output)

    elif args.command == 'split':
        chapters = get_m4b_chapters(args.m4b_file)
        if not chapters:
            print("Error: No chapters found. Use chapter detection first.")
            return 1

        split_m4b_by_chapters(
            args.m4b_file,
            chapters,
            output_dir=args.output_dir,
            output_format=args.format
        )

    elif args.command == 'info':
        print(f"\n=== M4B File Info: {args.m4b_file.name} ===\n")

        # Get metadata
        metadata = get_m4b_metadata(args.m4b_file)
        if metadata:
            print("Metadata:")
            for key, value in metadata.items():
                print(f"  {key}: {value}")

        # Get chapters
        chapters = get_m4b_chapters(args.m4b_file)
        if chapters:
            print(f"\nChapters: {len(chapters)}")
            for i, chapter in enumerate(chapters[:10], 1):  # Show first 10
                print(f"  {i}. {chapter['chapter_type']}")
            if len(chapters) > 10:
                print(f"  ... and {len(chapters) - 10} more")
        else:
            print("\nNo embedded chapters found")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
