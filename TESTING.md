# Testing Guide

## Running Tests

This project includes comprehensive unit tests to ensure code quality and reliability.

### Prerequisites

Install test dependencies:

```bash
pip install -r requirements.txt
```

This will install `pytest` along with other dependencies.

### Running All Tests

To run all tests:

```bash
python -m pytest test_chapterize_ab.py -v
```

### Running Specific Test Classes

To run a specific test class:

```bash
python -m pytest test_chapterize_ab.py::TestConfig -v
python -m pytest test_chapterize_ab.py::TestConvertTime -v
python -m pytest test_chapterize_ab.py::TestParseTimecodes -v
```

### Running Specific Tests

To run a specific test:

```bash
python -m pytest test_chapterize_ab.py::TestConfig::test_config_defaults -v
```

### Test Coverage

To see test coverage:

```bash
pip install pytest-cov
python -m pytest test_chapterize_ab.py --cov=chapterize_ab --cov-report=html
```

Then open `htmlcov/index.html` in your browser.

### Continuous Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements.txt
    python -m pytest test_chapterize_ab.py -v
```

## Test Structure

The test suite is organized into the following classes:

- **TestConfig**: Configuration validation and defaults
- **TestPathExists**: Path validation utilities
- **TestVerifyLanguage**: Language verification logic
- **TestVerifyDownload**: Model download verification
- **TestConvertTime**: Time conversion and formatting
- **TestParseTimecodes**: SRT timecode parsing
- **TestCueFileOperations**: Cue file reading/writing
- **TestParseConfig**: TOML configuration parsing
- **TestIntegration**: End-to-end integration tests

## Writing New Tests

When adding new features, please include corresponding tests:

```python
def test_my_new_feature():
    """Test description."""
    # Arrange
    input_data = ...

    # Act
    result = my_function(input_data)

    # Assert
    assert result == expected_value
```

Use pytest fixtures for common setup:

```python
@pytest.fixture
def sample_audiobook(tmp_path):
    """Create a sample audiobook file for testing."""
    file_path = tmp_path / "audiobook.mp3"
    file_path.write_bytes(b"fake audio data")
    return file_path
```
