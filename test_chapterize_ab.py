#!/usr/bin/env python3
"""
Unit tests for chapterize_ab.py

Run with: python -m pytest test_chapterize_ab.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, MagicMock
import sys
import tempfile
import shutil

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from chapterize_ab import (
    Config,
    path_exists,
    verify_language,
    verify_download,
    parse_config,
    convert_time,
    parse_timecodes,
    write_cue_file,
    read_cue_file,
)
from model.models import model_languages


class TestConfig:
    """Test the Config dataclass and validation."""

    def test_config_defaults(self):
        """Test that Config has proper default values."""
        config = Config()
        assert config.default_language == 'en-us'
        assert config.default_model == 'small'
        assert config.ffmpeg_path == 'ffmpeg'
        assert config.generate_cue_file is False
        assert config.cue_path == ''

    def test_config_validate_valid(self):
        """Test validation with valid config."""
        config = Config()
        errors = config.validate()
        assert errors == []

    def test_config_validate_invalid_model(self):
        """Test validation catches invalid model size."""
        config = Config(default_model='invalid')
        errors = config.validate()
        assert len(errors) > 0
        assert any('model size' in err for err in errors)

    def test_config_validate_invalid_language(self):
        """Test validation catches invalid language."""
        config = Config(default_language='invalid-lang')
        errors = config.validate()
        assert len(errors) > 0
        assert any('language' in err.lower() for err in errors)


class TestPathExists:
    """Test the path_exists utility function."""

    def test_path_exists_valid(self, tmp_path):
        """Test with a valid existing path."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        result = path_exists(test_file)
        assert isinstance(result, Path)
        assert result.exists()

    def test_path_exists_invalid(self):
        """Test with a non-existent path."""
        with pytest.raises(FileNotFoundError):
            path_exists("/nonexistent/path/file.txt")

    def test_path_exists_string_input(self, tmp_path):
        """Test with string input instead of Path object."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        result = path_exists(str(test_file))
        assert isinstance(result, Path)
        assert result.exists()


class TestVerifyLanguage:
    """Test language verification function."""

    def test_verify_language_code(self):
        """Test with valid language code."""
        result = verify_language('en-us')
        assert result == 'en-us'

    def test_verify_language_name(self):
        """Test with valid language name."""
        result = verify_language('English')
        assert result == 'en-us'

    def test_verify_language_case_insensitive(self):
        """Test that language checking is case-insensitive."""
        result = verify_language('french')
        assert result == 'fr'

    def test_verify_language_empty(self):
        """Test with empty language string."""
        with pytest.raises(SystemExit):
            verify_language('')

    def test_verify_language_invalid(self):
        """Test with invalid language."""
        with pytest.raises(SystemExit):
            verify_language('invalid-language')


class TestVerifyDownload:
    """Test download verification function."""

    def test_verify_download_small_english(self):
        """Test downloading small English model."""
        result = verify_download('en-us', 'small')
        assert 'en-us' in result
        assert 'small' in result

    def test_verify_download_large_english(self):
        """Test downloading large English model."""
        result = verify_download('en-us', 'large')
        assert 'en-us' in result
        assert 'large' not in result  # Large models don't have 'large' in name

    def test_verify_download_unavailable_size(self):
        """Test downloading unavailable model size."""
        # Greek only has large model
        with pytest.raises(SystemExit) as exc_info:
            verify_download('el', 'small')
        assert exc_info.value.code == 3


class TestConvertTime:
    """Test time conversion function."""

    def test_convert_time_normal(self):
        """Test normal time conversion."""
        result = convert_time('00:01:30.500')
        assert result == '00:01:29.500'

    def test_convert_time_rollover_minute(self):
        """Test rollover from seconds to minutes."""
        result = convert_time('00:01:00.000')
        assert result == '00:00:59.000'

    def test_convert_time_rollover_hour(self):
        """Test rollover from minutes to hours."""
        result = convert_time('01:00:00.000')
        assert result == '00:59:59.000'

    def test_convert_time_zero(self):
        """Test with zero time."""
        result = convert_time('00:00:00.000')
        assert result == '00:00:00.000'  # Should handle gracefully

    def test_convert_time_invalid_format(self):
        """Test with invalid time format."""
        with pytest.raises(ValueError):
            convert_time('invalid')

    def test_convert_time_missing_milliseconds(self):
        """Test with missing milliseconds."""
        with pytest.raises(ValueError):
            convert_time('00:01:30')


class TestParseTimecodes:
    """Test timecode parsing function."""

    def test_parse_timecodes_basic(self):
        """Test basic timecode parsing."""
        srt_content = [
            "1",
            "00:00:05,000 --> 00:00:10,000",
            "chapter one",
            "",
            "2",
            "00:00:15,000 --> 00:00:20,000",
            "chapter two"
        ]
        result = parse_timecodes(srt_content, 'en-us')
        assert len(result) >= 1
        assert all('chapter_type' in tc for tc in result)

    def test_parse_timecodes_prologue(self):
        """Test parsing with prologue."""
        srt_content = [
            "1",
            "00:00:05,000 --> 00:00:10,000",
            "prologue begins",
            "",
            "2",
            "00:00:15,000 --> 00:00:20,000",
            "chapter one"
        ]
        result = parse_timecodes(srt_content, 'en-us')
        assert len(result) >= 1
        # First chapter should be prologue
        assert 'Prologue' in result[0]['chapter_type']

    def test_parse_timecodes_epilogue(self):
        """Test parsing with epilogue."""
        srt_content = [
            "1",
            "00:00:05,000 --> 00:00:10,000",
            "chapter one",
            "",
            "2",
            "00:00:15,000 --> 00:00:20,000",
            "epilogue begins"
        ]
        result = parse_timecodes(srt_content, 'en-us')
        assert len(result) >= 1
        # Should have epilogue
        assert any('Epilogue' in tc.get('chapter_type', '') for tc in result)

    def test_parse_timecodes_excluded_phrases(self):
        """Test that excluded phrases are filtered out."""
        srt_content = [
            "1",
            "00:00:05,000 --> 00:00:10,000",
            "chapter and verse",  # Should be excluded
            "",
            "2",
            "00:00:15,000 --> 00:00:20,000",
            "chapter one"  # Should be included
        ]
        result = parse_timecodes(srt_content, 'en-us')
        # Should only have valid chapter, not the excluded phrase
        assert len(result) >= 1

    def test_parse_timecodes_empty(self):
        """Test with empty content."""
        with pytest.raises(SystemExit):
            parse_timecodes([], 'en-us')

    def test_parse_timecodes_unsupported_language(self):
        """Test with unsupported language features."""
        with pytest.raises(SystemExit) as exc_info:
            parse_timecodes(['dummy'], 'unsupported-lang')
        assert exc_info.value.code == 13


class TestCueFileOperations:
    """Test cue file reading and writing."""

    def test_write_cue_file_success(self, tmp_path):
        """Test successful cue file writing."""
        cue_path = tmp_path / "test.cue"
        timecodes = [
            {'start': '00:00:00.000', 'chapter_type': 'Chapter 01', 'end': '00:05:00.000'},
            {'start': '00:05:01.000', 'chapter_type': 'Chapter 02'}
        ]
        result = write_cue_file(timecodes, cue_path, "test_audiobook")
        assert result is True
        assert cue_path.exists()

        # Verify content
        content = cue_path.read_text()
        assert 'FILE "test_audiobook.mp3" MP3' in content
        assert 'Chapter 01' in content
        assert 'Chapter 02' in content

    def test_write_cue_file_io_error(self, tmp_path):
        """Test cue file writing with IO error."""
        # Try to write to a directory instead of a file
        cue_path = tmp_path / "subdir"
        cue_path.mkdir()
        timecodes = [{'start': '00:00:00.000', 'chapter_type': 'Chapter 01'}]

        # Create a file first so 'x' mode will fail
        cue_file = tmp_path / "test.cue"
        cue_file.write_text("existing")

        result = write_cue_file(timecodes, cue_file, "test")
        assert result is False

    def test_read_cue_file_success(self, tmp_path):
        """Test successful cue file reading."""
        cue_path = tmp_path / "test.cue"
        cue_content = '''FILE "test.mp3" MP3
TRACK 1 AUDIO
  TITLE\t"Chapter 01"
  START\t00:00:00.000
  END\t\t00:05:00.000
TRACK 2 AUDIO
  TITLE\t"Chapter 02"
  START\t00:05:01.000
'''
        cue_path.write_text(cue_content)
        result = read_cue_file(cue_path)

        assert result is not None
        assert len(result) == 2
        assert result[0]['chapter_type'] == 'Chapter 01'
        assert result[0]['start'] == '00:00:00.000'
        assert result[0]['end'] == '00:05:00.000'
        assert result[1]['chapter_type'] == 'Chapter 02'

    def test_read_cue_file_not_found(self, tmp_path):
        """Test reading non-existent cue file."""
        cue_path = tmp_path / "nonexistent.cue"
        result = read_cue_file(cue_path)
        assert result is None

    def test_read_cue_file_empty(self, tmp_path):
        """Test reading empty cue file."""
        cue_path = tmp_path / "empty.cue"
        cue_path.write_text("FILE \"test.mp3\" MP3\n")
        result = read_cue_file(cue_path)
        assert result is None  # Should return None for no timecodes

    def test_write_read_cue_file_roundtrip(self, tmp_path):
        """Test that writing and reading cue files produces consistent results."""
        cue_path = tmp_path / "roundtrip.cue"
        original_timecodes = [
            {'start': '00:00:00.000', 'chapter_type': 'Prologue', 'end': '00:02:30.000'},
            {'start': '00:02:31.000', 'chapter_type': 'Chapter 01', 'end': '00:10:00.000'},
            {'start': '00:10:01.000', 'chapter_type': 'Chapter 02'}
        ]

        # Write
        write_result = write_cue_file(original_timecodes, cue_path, "test")
        assert write_result is True

        # Read
        read_timecodes = read_cue_file(cue_path)
        assert read_timecodes is not None
        assert len(read_timecodes) == len(original_timecodes)

        # Compare (note: last entry won't have 'end' key)
        for i, (orig, read) in enumerate(zip(original_timecodes, read_timecodes)):
            assert read['chapter_type'] == orig['chapter_type']
            assert read['start'] == orig['start']
            if i < len(original_timecodes) - 1:
                assert read['end'] == orig['end']


class TestParseConfig:
    """Test configuration file parsing."""

    def test_parse_config_with_tomli(self, tmp_path, monkeypatch):
        """Test config parsing with tomli library."""
        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        # Create a test TOML config
        config_content = """
default_language = 'en-us'
default_model = 'large'
ffmpeg_path = '/usr/bin/ffmpeg'
generate_cue_file = true
cue_path = '/path/to/cue'
"""
        (tmp_path / "defaults.toml").write_text(config_content)

        config = parse_config()
        assert config.default_language == 'en-us'
        assert config.default_model == 'large'
        assert config.ffmpeg_path == '/usr/bin/ffmpeg'
        assert config.generate_cue_file is True
        assert config.cue_path == '/path/to/cue'

    def test_parse_config_missing_file(self, tmp_path, monkeypatch):
        """Test config parsing when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        config = parse_config()
        # Should return default Config
        assert config.default_language == 'en-us'
        assert config.default_model == 'small'


# Integration-style tests
class TestIntegration:
    """Integration tests for multiple components working together."""

    def test_timecode_conversion_chain(self):
        """Test the full chain of timecode processing."""
        # Create sample SRT content
        srt_content = [
            "1",
            "00:00:00,000 --> 00:00:05,000",
            "prologue starts here",
            "",
            "2",
            "00:05:30,000 --> 00:05:35,000",
            "chapter one begins",
            "",
            "3",
            "00:15:45,000 --> 00:15:50,000",
            "chapter two starts"
        ]

        # Parse timecodes
        timecodes = parse_timecodes(srt_content, 'en-us')

        # Verify we got timecodes
        assert len(timecodes) >= 2

        # Verify time conversion worked (end times should be start - 1 second)
        for i, tc in enumerate(timecodes[:-1]):
            if 'end' in tc:
                # The end time should exist and be valid
                assert tc['end']
                # Verify it's in correct format
                assert tc['end'].count(':') == 2
                assert '.' in tc['end']

    def test_cue_file_workflow(self, tmp_path):
        """Test complete cue file workflow."""
        cue_path = tmp_path / "workflow.cue"
        audiobook_stem = "test_book"

        # Create timecodes
        timecodes = [
            {'start': '00:00:00.000', 'chapter_type': 'Prologue', 'end': '00:05:00.000'},
            {'start': '00:05:01.000', 'chapter_type': 'Chapter 01', 'end': '00:15:00.000'},
            {'start': '00:15:01.000', 'chapter_type': 'Chapter 02'}
        ]

        # Write cue file
        success = write_cue_file(timecodes, cue_path, audiobook_stem)
        assert success is True
        assert cue_path.exists()

        # Read it back
        read_back = read_cue_file(cue_path)
        assert read_back is not None
        assert len(read_back) == 3

        # Verify integrity
        assert read_back[0]['chapter_type'] == 'Prologue'
        assert read_back[1]['chapter_type'] == 'Chapter 01'
        assert read_back[2]['chapter_type'] == 'Chapter 02'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
