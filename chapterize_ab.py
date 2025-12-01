#!/usr/bin/env python3

import re
import subprocess
import argparse
import sys
from typing import Optional
from pathlib import Path
from shutil import unpack_archive, copytree, rmtree, which
from datetime import datetime, timedelta
from dataclasses import dataclass

# Handle tomli/tomllib for different Python versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

from rich.console import Console
from rich.pretty import Pretty
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    BarColumn,
    DownloadColumn,
    TimeRemainingColumn,
    Progress,
    TextColumn,
    MofNCompleteColumn
)
from vosk import Model, KaldiRecognizer, SetLogLevel

# Local imports
from model.models import (
    models_small,
    models_large,
    model_languages,
    get_language_features
)

'''
    Constants
'''

__version__ = '0.7.0'
__author__ = 'patrickenfuego'

# Audio processing constants
SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1

# Download chunk sizes (in bytes)
CHUNK_SIZE_SMALL = 50
CHUNK_SIZE_LARGE = 300

# File size thresholds
MIN_METADATA_SIZE = 10
MIN_COVER_ART_SIZE = 10

# URLs
VOSK_URL = "https://alphacephei.com/vosk/models"
vosk_link = f"[link={VOSK_URL}]this link[/link]"

# Console
con = Console()


'''
    Configuration Management
'''


@dataclass
class Config:
    """Configuration settings for the application."""
    default_language: str = 'en-us'
    default_model: str = 'small'
    ffmpeg_path: str = 'ffmpeg'
    generate_cue_file: bool = False
    cue_path: str = ''

    def validate(self) -> list[str]:
        """Validate configuration values.

        :return: List of validation error messages
        """
        errors = []

        if self.default_model not in ('small', 'large'):
            errors.append(
                f"Invalid model size in config file: '{self.default_model}'. "
                "Must be 'small' or 'large'."
            )

        if self.default_language not in model_languages.values():
            errors.append(
                f"Invalid language in config file: '{self.default_language}'"
            )

        if self.generate_cue_file and not isinstance(self.generate_cue_file, bool):
            errors.append("generate_cue_file must be a boolean value")

        return errors


'''
    Utility Function Declarations
'''


def path_exists(path: Path | str) -> Path:
    """Utility function to check if a path exists. Used by argparse.

    :param path: File path to verify
    :return: The tested file path if it exists
    :raises argparse.ArgumentTypeError: If the path does not exist
    """
    path_obj = Path(path)
    if path_obj.exists():
        return path_obj
    else:
        # Use ArgumentTypeError for better argparse integration
        raise argparse.ArgumentTypeError(
            f"\n\n"
            f"  File not found: {path}\n\n"
            f"  Please check:\n"
            f"    - The file path is correct\n"
            f"    - The file exists at the specified location\n"
            f"    - You have permission to access the file\n"
        )


def verify_language(language: str) -> str:
    """Verifies that the selected language is valid.

    Used to confirm that the language passed via argparse is valid and also supported
    in the list of downloadable model files if the download option is selected.

    :param language: Model language
    :return: The language string if it is a supported language
    """
    if not language:
        con.print("[bold red]ERROR:[/] Language option appears to be empty")
        sys.exit(1)

    code = ''

    if language.lower() in model_languages.values():
        code = language.lower()
    elif language.title() in model_languages.keys():
        code = model_languages[language.title()]
    else:
        con.print("[bold red]ERROR:[/] Invalid language or language code entered. Possible options:")
        print("\n")
        con.print(Panel(Pretty(model_languages), title="Supported Languages & Codes"))
        print("\n")
        sys.exit(2)

    return code


def verify_download(language: str, model_type: str) -> str:
    """Verifies that the selected language can be downloaded by the script.

    If the download option is selected, this function verifies that the language
    model and size are supported by the script.

    :param language: Language of the model to download.
    :param model_type: Type of model (small or large).
    :return: String name of the model file to download if supported.
    """
    lang_code = verify_language(language)
    name = ''
    other = 'small' if model_type == 'large' else 'large'

    # Search for the model in the appropriate list
    model_list = models_small if model_type == 'small' else models_large
    for line in model_list:
        if lang_code in line:
            name = line
            break

    # If the specified model wasn't found, check for a different size
    if not name:
        alt_list = models_large if model_type == 'small' else models_small
        found_alt = any(lang_code in line for line in alt_list)

        if found_alt:
            con.print(
                f"[bold yellow]WARNING:[/] The selected model cannot be downloaded for '{language}' "
                f"in the specified size '{model_type}'. However, a '{other}' model was found. "
                f"You can re-run the script and choose {other}, or attempt to "
                f"download a different model manually from {vosk_link}."
            )
            sys.exit(3)
        else:
            con.print(
                f"[bold red]ERROR:[/] The selected model cannot be downloaded for '{language}' "
                f"in size {model_type}. You can try and download a different model manually "
                f"from {vosk_link}."
            )
            sys.exit(33)

    return name


def parse_config() -> Config:
    """Parses the TOML config file.

    :return: A Config object containing the configuration settings.
    :raises SystemExit: If config file doesn't exist or can't be parsed
    """
    config_path = Path.cwd() / 'defaults.toml'

    if not config_path.exists():
        con.print(
            "[bold red]ERROR:[/] Could not locate [blue]defaults.toml[/] file. "
            "Did you move or delete it?"
        )
        print("\n")
        return Config()

    # Use proper TOML library
    if tomllib is None:
        con.print(
            "[bold yellow]WARNING:[/] tomli library not available. "
            "Install with: pip install tomli"
        )
        con.print("[yellow]Falling back to basic parsing[/]")

        # Fallback to simple parsing
        try:
            with open(config_path, 'r') as fp:
                lines = fp.readlines()
            defaults = {}
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    defaults[key.strip()] = value.strip().strip("'\"")

            return Config(
                default_language=defaults.get('default_language', 'en-us'),
                default_model=defaults.get('default_model', 'small'),
                ffmpeg_path=defaults.get('ffmpeg_path', 'ffmpeg'),
                generate_cue_file=defaults.get('generate_cue_file', 'False') == 'True',
                cue_path=defaults.get('cue_path', '')
            )
        except (ValueError, KeyError) as e:
            con.print(f"[bold red]ERROR:[/] Failed to parse config file: {e}")
            return Config()

    # Use proper TOML parsing
    try:
        with open(config_path, 'rb') as fp:
            data = tomllib.load(fp)

        config = Config(
            default_language=data.get('default_language', 'en-us'),
            default_model=data.get('default_model', 'small'),
            ffmpeg_path=data.get('ffmpeg_path', 'ffmpeg'),
            generate_cue_file=data.get('generate_cue_file', False),
            cue_path=data.get('cue_path', '')
        )

        # Validate configuration
        if errors := config.validate():
            con.print("[bold yellow]WARNING:[/] Configuration validation errors:")
            for error in errors:
                con.print(f"  - {error}")
            con.print("[yellow]Using default values for invalid settings[/]")
            # Reset invalid values to defaults
            if config.default_model not in ('small', 'large'):
                config.default_model = 'small'

        return config

    except (tomllib.TOMLDecodeError, OSError) as e:
        con.print(f"[bold red]ERROR:[/] Failed to parse TOML config: {e}")
        return Config()


def get_ffmpeg_path(config: Config) -> str:
    """Determine the ffmpeg executable path.

    :param config: Configuration object
    :return: Path to ffmpeg executable
    :raises SystemExit: If ffmpeg cannot be found
    """
    # Try config path first
    if config.ffmpeg_path and config.ffmpeg_path != 'ffmpeg':
        if Path(config.ffmpeg_path).exists():
            return str(config.ffmpeg_path)
        else:
            con.print(
                "[yellow]NOTE:[/] ffmpeg path in [blue]defaults.toml[/] does not exist"
            )

    # Try system PATH
    if ffmpeg_path := which('ffmpeg'):
        if config.ffmpeg_path and config.ffmpeg_path != 'ffmpeg':
            con.print(
                f"[yellow]NOTE:[/] Found ffmpeg in system PATH: [green]{ffmpeg_path}[/]"
            )
        return 'ffmpeg'

    # Not found
    con.print("[bold red]CRITICAL:[/] ffmpeg was not found in config file or system PATH. Aborting")
    sys.exit(1)


'''
    Function Declarations
'''


def parse_args():
    """
    Parses command line arguments.

    :return: A tuple containing the audiobook path, metadata, language, model info, and cue file path
    """
    parser = argparse.ArgumentParser(
        description='''
        Splits a single monolithic mp3 audiobook file into multiple chapter files using Machine Learning.
        Metadata and cover art are also extracted from the source file, but any user supplied values
        automatically take precedence when conflicts arise.
        '''
    )
    parser.add_argument('audiobook', nargs='?', metavar='AUDIOBOOK_PATH',
                        type=path_exists, help='Path to audiobook file. Positional argument. Required')
    parser.add_argument('--timecodes_file', '-tc', nargs='?', metavar='TIMECODES_FILE',
                        type=path_exists, dest='timecodes',
                        help='Path to generated srt timecode file (if ran previously in a different directory)')
    parser.add_argument('--language', '-l', dest='lang', nargs='?', default='en-us',
                        metavar='LANGUAGE', type=verify_language,
                        help='Model language to use (en-us provided). See the --download_model parameter.')
    parser.add_argument('--model', '-m', dest='model_type', nargs='?', default='small',
                        type=str, choices=['small', 'large'],
                        help='Model type to use if multiple models are available. Default is small.')
    parser.add_argument('--list_languages', '-ll', action='store_true', help='List supported languages and exit')
    parser.add_argument('--download_model', '-dm', choices=['small', 'large'], dest='download',
                        nargs='?', default=argparse.SUPPRESS,
                        help='Download the model archive specified in the --language parameter')
    parser.add_argument('--cover_art', '-ca', dest='cover_art', nargs='?', default=None,
                        metavar='COVER_ART_PATH', type=path_exists, help='Path to cover art file. Optional')
    parser.add_argument('--author', '-a', dest='author', nargs='?', default=None,
                        metavar='AUTHOR', type=str, help='Author. Optional metadata field')
    parser.add_argument('--description', '-d', dest='description', nargs='?', default=None,
                        metavar='DESCRIPTION', type=str, help='Book description. Optional metadata field')
    parser.add_argument('--title', '-t', dest='title', nargs='?', default=None,
                        metavar='TITLE', type=str, help='Audiobook title. Metadata field')
    parser.add_argument('--narrator', '-n', dest='narrator', nargs='?', default=None,
                        metavar='NARRATOR', type=str, help='Narrator of the audiobook. Saves as the "Composer" ID3 tag')
    parser.add_argument('--genre', '-g', dest='genre', nargs='?', default='Audiobook',
                        metavar='GENRE', type=str,
                        help='Audiobook genre. Separate multiple genres using a semicolon. Multiple genres can be passed as a string delimited by ";". Optional metadata field')
    parser.add_argument('--year', '-y', dest='year', nargs='?', default=None,
                        metavar='YEAR', type=str, help='Audiobook release year. Optional metadata field')
    parser.add_argument('--comment', '-c', dest='comment', nargs='?', default=None,
                        metavar='COMMENT', type=str, help='Audiobook comment. Optional metadata field')
    parser.add_argument('--write_cue_file', '-wc', action='store_true', dest='write_cue',
                        help='Generate a cue file in the audiobook directory for editing chapter markers. Can also be set in defaults.toml. Default disabled')
    parser.add_argument('--cue_path', '-cp', nargs='?', default=None, metavar='CUE_PATH', type=path_exists,
                        help='Path to cue file in non-default location (i.e., not in the audiobook directory) containing chapter timecodes. Can also be set in defaults.toml, which has lesser precedence than this argument')
    parser.add_argument('--use-existing-chapters', '-uec', action='store_true', dest='use_existing',
                        help='For M4B files: automatically use existing embedded chapters without prompting')

    args = parser.parse_args()
    config = parse_config()

    # Check if audiobook file was provided
    if not args.audiobook:
        con.print("\n[bold red]ERROR:[/] No audiobook file specified\n")
        con.print("[yellow]Usage:[/]")
        con.print("  python chapterize_ab.py <audiobook_file> [options]\n")
        con.print("[yellow]Example:[/]")
        con.print("  python chapterize_ab.py audiobook.mp3 --title \"My Book\"\n")
        con.print("[yellow]Supported formats:[/] .mp3, .m4b, .m4a\n")
        parser.print_help()
        sys.exit(1)

    if args.list_languages:
        con.print(Panel(Pretty(model_languages), title="Supported Languages & Codes"))
        print("\n")
        con.print(
            "[yellow]NOTE:[/] The languages listed are supported by the "
            "[bold green]--download_model[/]/[bold green]-dm[/] parameter (either small, large, or both). "
            f"You can find additional models at {vosk_link}."
        )
        print("\n")
        sys.exit(0)

    model_name = ''
    download = ''

    if 'download' in args:
        if args.lang == 'en-us':
            con.print(
                "[bold yellow]WARNING:[/] [bold green]--download_model[/] was used, but a language was not set. "
                "the default value [cyan]'en-us'[/] will be used. If you want a different language, use the "
                "[bold blue]--language[/] option to specify one."
            )

        download = 'small' if args.download not in ['small', 'large'] else args.download
        model_name = verify_download(args.lang, download)

    # Set ID3 metadata fields based on passed args
    meta_fields = {'cover_art': args.cover_art if args.cover_art else None,
                   'genre': args.genre}
    if args.author:
        meta_fields['album_artist'] = args.author
    if args.title:
        meta_fields['album'] = args.title
    if args.year:
        meta_fields['date'] = args.year
    if args.comment:
        meta_fields['comment'] = args.comment
    if args.description:
        meta_fields['description'] = args.description
    if args.narrator:
        meta_fields['narrator'] = args.narrator

    # Determine model type
    if download:
        model_type = download
    elif 'model_type' in args:
        model_type = args.model_type
    else:
        model_type = config.default_model

    # Check if cue file write is enabled, if custom path was passed, or if cue already exists
    if args.cue_path:
        cue_file = args.cue_path
        con.print(
            f"[bright_magenta]Cue file <<[/] [blue]custom path[/]: Reading cue file from [green]{cue_file}[/]"
        )
    elif config.cue_path:
        if not Path(config.cue_path).exists():
            con.print(
                "[bold yellow]WARNING:[/] Cue file in [blue]defaults.toml[/] does not exist and will be skipped"
            )
            cue_file = None
        else:
            cue_file = Path(config.cue_path)
            con.print(
                f"[bright_magenta]Cue file <<[/] [blue]default.toml[/]: Reading cue file from [green]{cue_file}[/]"
            )
    elif (
            args.write_cue or
            config.generate_cue_file or
            args.audiobook.with_suffix('.cue').exists()
        ):
        cue_file = args.audiobook.with_suffix('.cue')
        method = ('Writing', 'to') if not cue_file.exists() else ('Reading', 'from')
        con.print(f"[bright_magenta]Cue file[/]: {method[0]} cue file {method[1]} [green]{cue_file}[/]")
    else:
        cue_file = None

    if cue_file:
        print("\n")

    # Determine language
    if 'lang' in args:
        language = args.lang
    else:
        language = verify_language(config.default_language)

    # Get ffmpeg path
    ffmpeg = get_ffmpeg_path(config)

    return args.audiobook, meta_fields, language, model_name, model_type, cue_file, ffmpeg, args.use_existing


def build_progress(bar_type: str) -> Progress:
    """Builds a progress bar object and returns it.

    :param bar_type: Type of progress bar.
    :return: a Progress object
    :raises ValueError: If bar_type is unknown
    """
    text_column = TextColumn(
        "[bold blue]{task.fields[verb]}[/] [bold magenta]{task.fields[noun]}",
        justify="right"
    )

    if bar_type == 'chapterize':
        progress = Progress(
            text_column,
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            MofNCompleteColumn(),
            "•",
            TimeRemainingColumn()
        )
    elif bar_type == 'download':
        progress = Progress(
            text_column,
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn()
        )
    else:
        raise ValueError(f"Unknown progress bar type: {bar_type}")

    return progress


def print_table(list_dicts: list[dict]) -> None:
    """Formats a list of dictionaries into a table. Currently only used for timecodes.

    :param list_dicts: List of dictionaries to format
    """
    table = Table(
        title='[bold magenta]Parsed Timecodes for Chapters[/]',
        caption='[red]EOF[/] = End of File'
    )
    table.add_column('Start')
    table.add_column('End')
    table.add_column('Chapter')

    merge_rows = []
    for item in list_dicts:
        row = []
        for v in item.values():
            row.append(v)
        merge_rows.append(row)

    if len(merge_rows[-1]) != 3:
        merge_rows[-1].append('EOF')
    for row in merge_rows:
        table.add_row(f"[green]{str(row[0])}", f"[red]{str(row[2])}", f"[bright_blue]{str(row[1])}")

    con.print(table)


def extract_metadata(audiobook_path: Path, ffmpeg: str) -> dict:
    """Extracts existing metadata from the input file.

    :param audiobook_path: Path to the input audiobook file
    :param ffmpeg: Path to ffmpeg executable
    :return: A dictionary containing metadata values
    """
    metadata_file = audiobook_path.parent / 'metadata.txt'

    # Extract metadata to file using ffmpeg
    try:
        subprocess.run(
            [ffmpeg, '-y', '-loglevel', 'quiet', '-i', str(audiobook_path),
             '-f', 'ffmetadata', str(metadata_file)],
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        con.print(f"[bold yellow]WARNING:[/] Failed to extract metadata: {e}")
        return {}

    meta_dict = {}
    # If path exists and has some content
    try:
        if metadata_file.exists() and metadata_file.stat().st_size > MIN_METADATA_SIZE:
            con.print("[bold green]SUCCESS![/] Metadata extraction complete")
            with open(metadata_file, 'r', encoding='utf-8', errors='ignore') as fp:
                meta_lines = fp.readlines()

            for line in meta_lines:
                if '=' not in line:
                    continue
                parts = line.split('=', 1)
                if len(parts) == 2:
                    key, value = [x.strip() for x in parts]
                    if key in ['title', 'genre', 'album_artist', 'artist', 'album', 'year']:
                        meta_dict[key] = value
        else:
            con.print("[bold yellow]WARNING:[/] Failed to parse metadata file, or none was found")
    except (OSError, UnicodeDecodeError) as e:
        con.print(f"[bold yellow]WARNING:[/] Error reading metadata file: {e}")
    finally:
        # Delete the metadata file once done
        if metadata_file.exists():
            try:
                metadata_file.unlink()
            except OSError:
                pass

    return meta_dict


def extract_coverart(audiobook_path: Path, ffmpeg: str) -> Optional[Path]:
    """Extract cover art file from audiobook if present.

    :param audiobook_path: Input audiobook file
    :param ffmpeg: Path to ffmpeg executable
    :return: Path to cover art jpg file if found, otherwise None
    """
    cover_art = audiobook_path.with_suffix('.jpg')

    try:
        subprocess.run(
            [ffmpeg, '-y', '-loglevel', 'quiet', '-i', str(audiobook_path),
             '-an', '-c:v', 'copy', str(cover_art)],
            check=True,
            capture_output=True
        )

        if cover_art.exists() and cover_art.stat().st_size > MIN_COVER_ART_SIZE:
            con.print("[bold green]SUCCESS![/] Cover art extracted")
            print("\n")
            return cover_art
        else:
            con.print("[bold yellow]WARNING:[/] Failed to extract cover art, or none was found")
            print("\n")
            return None

    except subprocess.CalledProcessError:
        con.print("[bold yellow]WARNING:[/] Failed to extract cover art, or none was found")
        print("\n")
        return None


def download_model(name: str) -> None:
    """Downloads the specified language model from vosk (if available).

    :param name: Name of the model found on the vosk website
    :raises SystemExit: If download fails or requests library is unavailable
    """
    try:
        import requests
        from requests.exceptions import ConnectionError as ReqConnectionError, RequestException
    except ImportError:
        con.print(
            "[bold red]CRITICAL:[/] requests library is not available, and is required for "
            "downloading models. Run [bold green]pip install requests[/] and re-run the script."
        )
        sys.exit(18)

    full_url = f'{VOSK_URL}/{name}.zip'
    out_base = Path(__file__).parent.absolute() / 'model'
    out_zip = out_base / f'{name}.zip'
    out_dir = out_base / name

    if out_dir.exists():
        con.print("[bold yellow]it appears you already have the model downloaded. Sweet![/]")
        return

    progress = build_progress(bar_type='download')

    try:
        with requests.get(full_url, stream=True, allow_redirects=True, timeout=30) as req:
            if req.status_code != 200:
                raise ReqConnectionError(
                    f"Failed to download the model file: {full_url}. HTTP Response: {req.status_code}"
                )

            size = int(req.headers.get('Content-Length', 0))
            chunk_size = CHUNK_SIZE_SMALL if 'small' in name else CHUNK_SIZE_LARGE
            task = progress.add_task("", size=size, noun=name, verb='Downloading')
            progress.update(task, total=size)

            with open(out_zip, 'wb') as dest_file:
                with progress:
                    for chunk in req.iter_content(chunk_size=chunk_size * 1024):
                        if chunk:
                            dest_file.write(chunk)
                            progress.update(task, advance=len(chunk))
    except RequestException as e:
        con.print(f"[bold red]ERROR:[/] Failed to download model: {e}")
        sys.exit(19)

    try:
        unpack_archive(str(out_zip), str(out_dir))

        if out_dir.exists():
            con.print("[bold green]SUCCESS![/] Model downloaded and extracted successfully")
            print("\n")
            out_zip.unlink()

            # If it extracts inside another directory, copy up and remove extra
            child_dir = out_dir / name
            if child_dir.exists():
                temp_name = f"{name}-new"
                child_dir.rename(out_base / temp_name)
                child_dir_new = copytree(out_base / temp_name, out_base / temp_name + "-copy")
                rmtree(out_dir)
                child_dir_new.rename(out_dir)
        elif out_zip.exists() and not out_dir.exists():
            con.print(
                "[bold red]ERROR:[/] Model archive downloaded successfully, but failed to extract. "
                "Manually extract the archive into the model directory and re-run the script."
            )
            sys.exit(4)
        else:
            con.print(
                "[bold red]CRITICAL:[/] Model archive failed to download. The selected model "
                f"might not be supported by the script, or is unavailable. Follow {vosk_link} "
                "to download a model manually.\n"
            )
            sys.exit(5)
    except (OSError, ValueError) as e:
        con.print(f"[bold red]CRITICAL:[/] Failed to unpack or rename the model: {e}")
        sys.exit(29)


def convert_time(time: str) -> str:
    """Convert timecodes for chapter markings.

    Subtracts 1 second from the given time to create end markers.

    :param time: Timecode in format HH:MM:SS.mmm
    :return: Adjusted time marker
    :raises ValueError: If time format is invalid
    """
    try:
        # Parse the time string
        parts = time.split(':')
        if len(parts) != 3:
            raise ValueError(f"Invalid time format: {time}")

        last_part = parts[-1]
        if '.' not in last_part:
            raise ValueError(f"Missing milliseconds in time: {time}")

        seconds, milliseconds = last_part.split('.')

        # Create a timedelta and subtract 1 second
        hours = int(parts[0])
        minutes = int(parts[1])
        secs = int(seconds)

        # Convert to total seconds, subtract 1, then convert back
        total_seconds = hours * 3600 + minutes * 60 + secs - 1

        if total_seconds < 0:
            total_seconds = 0

        new_hours = total_seconds // 3600
        new_minutes = (total_seconds % 3600) // 60
        new_seconds = total_seconds % 60

        return f"{new_hours:02d}:{new_minutes:02d}:{new_seconds:02d}.{milliseconds}"

    except (ValueError, IndexError) as e:
        con.print(f"[bold red]ERROR:[/] Could not convert end chapter marker for {time}: {e}")
        raise


def split_file(audiobook_path: Path,
               timecodes: list[dict],
               metadata: dict,
               cover_art: Optional[Path],
               ffmpeg: str) -> None:
    """Splits a single audiobook file into chapterized segments.

    Supports MP3, M4B, and M4A formats. Output format matches input format
    to preserve codec quality with -c copy.

    :param audiobook_path: Path to original audiobook file
    :param timecodes: List of start/end markers for each chapter
    :param metadata: File metadata passed via CLI and/or parsed from audiobook file
    :param cover_art: Optional path to cover art
    :param ffmpeg: Path to ffmpeg executable
    """
    file_stem = audiobook_path.stem
    file_ext = audiobook_path.suffix.lower()

    # Determine output extension (must match input codec)
    # M4B/M4A use AAC codec, MP3 uses MP3 codec
    output_ext = file_ext if file_ext in ['.m4b', '.m4a'] else '.mp3'

    # Set the log path for output
    log_path = audiobook_path.parent / 'ffmpeg_log.txt'

    if log_path.exists():
        try:
            with open(log_path, 'a+', encoding='utf-8') as fp:
                fp.writelines([
                    '********************************************************\n',
                    'NEW LOG START\n',
                    '********************************************************\n\n'
                ])
        except OSError:
            pass

    command = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'info', '-i', str(audiobook_path)]

    # Handle cover art and stream mapping
    # Note: M4B/M4A containers don't support adding JPEG cover art via stream mapping
    # Cover art in M4B files is usually already embedded in the source
    if cover_art and output_ext == '.mp3':
        # MP3: Add cover art via ID3v2 tags
        command.extend(['-i', str(cover_art), '-id3v2_version', '3', '-metadata:s:v', 'comment="Cover (front)"'])
        stream = ['-map', '0:0', '-map', '1:0', '-c', 'copy']
    elif output_ext == '.mp3':
        # MP3 without cover art
        command.extend(['-id3v2_version', '3'])
        stream = ['-c', 'copy']
    else:
        # M4B/M4A: Just copy audio stream, skip external cover art
        # (Cover art from source M4B is preserved automatically with -c copy)
        stream = ['-c', 'copy']

    # Handle metadata strings if they exist
    if 'album_artist' in metadata:
        command.extend(['-metadata', f"album_artist={metadata['album_artist']}",
                        '-metadata', f"artist={metadata['album_artist']}"])
    if 'genre' in metadata:
        command.extend(['-metadata', f"genre={metadata['genre']}"])
    if 'album' in metadata:
        command.extend(['-metadata', f"album={metadata['album']}"])
    if 'date' in metadata:
        command.extend(['-metadata', f"date={metadata['date']}"])
    if 'comment' in metadata:
        command.extend(['-metadata', f"comment={metadata['comment']}"])
    if 'description' in metadata:
        command.extend(['-metadata', f"description={metadata['description']}"])
    if 'narrator' in metadata:
        command.extend(['-metadata', f"composer={metadata['narrator']}"])

    progress = build_progress(bar_type='chapterize')

    with progress:
        task = progress.add_task('', total=len(timecodes), verb='Processing', noun='Audiobook...')

        for counter, times in enumerate(timecodes, start=1):
            counter_str = f'{counter:02d}'
            command_copy = command.copy()

            if 'start' in times:
                command_copy[5:5] = ['-ss', times['start']]
            if 'end' in times:
                command_copy[7:7] = ['-to', times['end']]

            if 'chapter_type' in times:
                file_path = audiobook_path.parent / f"{file_stem} {counter_str} - {times['chapter_type']}{output_ext}"
            else:
                file_path = audiobook_path.parent / f"{file_stem} - {counter_str}{output_ext}"

            track_num = ['-metadata', f"track={counter}/{len(timecodes)}"]
            command_copy.extend([*stream, *track_num, '-metadata', f"title={times['chapter_type']}",
                                 str(file_path)])

            try:
                with open(log_path, 'a+', encoding='utf-8') as fp:
                    fp.write('----------------------------------------------------\n\n')
                    subprocess.run(command_copy, stdout=fp, stderr=fp, check=False)
            except OSError as e:
                con.print(
                    f"[bold red]ERROR:[/] An exception occurred writing logs to file: "
                    f"{e}\nOutputting to stdout..."
                )
                subprocess.run(command_copy, stdout=subprocess.STDOUT, check=False)

            progress.update(task, advance=1)


def generate_timecodes(audiobook_path: Path, language: str, model_type: str) -> Path:
    """Generate chapter timecodes using vosk Machine Learning API.

    This function searches for the specified model/language within the project's 'models' directory and
    uses it to perform a speech-to-text conversion on the audiobook, which is then saved in a subrip (srt) file.

    If more than 1 model is present, the script will attempt to guess which one to use based on input.

    :param audiobook_path: Path to input audiobook file
    :param language: Language used by the parser
    :param model_type: The type of model (large or small)
    :return: Path to timecode file
    :raises SystemExit: If model cannot be loaded or timecode generation fails
    """
    model_root = Path(__file__).parent / "model"

    # If the timecode file already exists, exit early and return path
    out_file = audiobook_path.with_suffix('.srt')
    if out_file.exists() and out_file.stat().st_size > MIN_METADATA_SIZE:
        con.print("[bold green]SUCCESS![/] An existing srt timecode file was found")
        print("\n")
        return out_file

    try:
        model_path = [d for d in model_root.iterdir() if d.is_dir() and language in d.stem]

        if model_path:
            print("\n")
            con.print(f":white_heavy_check_mark: Local ML model found. Language: '{language}'\n")

            # If there is more than 1 model, infer the proper one from the name
            if len(model_path) > 1:
                con.print(
                    f"[yellow]Multiple models for '{language}' found. "
                    f"Attempting to use the {model_type} model[/yellow]"
                )
                if model_type == 'small':
                    model_path = [d for d in model_path if 'small' in d.stem]
                else:
                    model_path = [d for d in model_path if 'small' not in d.stem]

                if not model_path:
                    raise IndexError("Could not find appropriate model size")

                model_path = model_path[0]
            else:
                model_path = model_path[0]
        else:
            raise IndexError("No model found for language")

    except (IndexError, OSError):
        con.print(
            "[bold yellow]WARNING:[/] Local ML model was not found (did you delete it?) "
            "or multiple models were found and the proper one couldn't be inferred.\n"
            "The script will attempt to download an online model, which "
            "isn't always reliable. Fair warning."
        )
        model_path = None

    SetLogLevel(-1)

    try:
        model = Model(lang=language, model_path=str(model_path) if model_path else None)
        rec = KaldiRecognizer(model, SAMPLE_RATE)
        rec.SetWords(True)
    except Exception as e:
        con.print(f"[bold red]ERROR:[/] Failed to load vosk model: {e}")
        sys.exit(7)

    try:
        # Get ffmpeg path
        ffmpeg = get_ffmpeg_path(parse_config())

        # Convert the file to wav format and stream output
        process = subprocess.Popen(
            [ffmpeg, "-loglevel", "quiet", "-i", str(audiobook_path),
             "-ar", str(SAMPLE_RATE), "-ac", str(AUDIO_CHANNELS), "-f", "s16le", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        with process.stdout as stream:
            with open(out_file, 'w+', encoding='utf-8') as fp:
                fp.writelines(rec.SrtResult(stream))

        # Wait for process to complete
        process.wait()

        if process.returncode != 0:
            stderr = process.stderr.read().decode('utf-8', errors='ignore') if process.stderr else ''
            con.print(f"[bold yellow]WARNING:[/] ffmpeg process exited with code {process.returncode}")
            if stderr:
                con.print(f"[yellow]Error output: {stderr[:200]}[/]")

        con.print("[bold green]SUCCESS![/] Timecode file created\n")

    except (OSError, Exception) as e:
        con.print(f"[bold red]ERROR:[/] Failed to generate timecode file with vosk: {e}\n")
        sys.exit(7)

    return out_file


def parse_timecodes(srt_content: list, language: str = 'en-us') -> list[dict]:
    """Parse the contents of the srt timecode file.

    Parses the output from `generate_timecodes` and generates start/end times, as well as chapter
    type (prologue, epilogue, etc.) if available.

    :param srt_content: List of timecodes extracted from the output of vosk
    :param language: Selected language. Used for importing excluded phrases
    :return: A list of dictionaries containing start, end, and chapter type data
    :raises SystemExit: If language features are not configured or no timecodes found
    """
    # Get lang specific markers and excluded phrases
    excluded_phrases, markers = get_language_features(language)

    # If language features are None, they haven't been defined
    if not excluded_phrases or not markers:
        from model.models import get_lang_from_code
        lang_str = get_lang_from_code(language)
        con.print(
            f"[bold red]CRITICAL:[/] Language features for [bright_blue]{lang_str.title()}[/] are not "
            "yet configured. If you speak this language, consider contributing to this project."
        )
        sys.exit(13)

    timecodes = []
    counter = 1

    for i, line in enumerate(srt_content):
        if (
                # Not the end of the list
                i != (len(srt_content) - 1) and
                # Doesn't contain an excluded phrase
                not any(x in srt_content[i+1] for x in excluded_phrases) and
                # Contains a marker substring
                any(m in srt_content[i+1] for m in markers)
        ):
            if start_regexp := re.search(r'\d\d:\d\d:\d\d,\d+(?=\s-)', line, flags=0):
                start = start_regexp.group(0).replace(',', '.')

                # Prologue
                if markers[0] in srt_content[i+1]:
                    chapter_type = markers[0].title()
                # Chapter X
                elif markers[1] in srt_content[i+1]:
                    # Add leading zero for better sorting if < 10
                    chapter_count = f'{counter:02d}'
                    chapter_type = f'{markers[1].title()} {chapter_count}'
                    counter += 1
                # Epilogue
                elif markers[2] in srt_content[i+1]:
                    chapter_type = markers[2].title()
                else:
                    chapter_type = ''

                # Build dict with start codes and marker
                if len(timecodes) == 0:
                    time_dict = {'start': '00:00:00.000', 'chapter_type': chapter_type}
                else:
                    time_dict = {'start': start, 'chapter_type': chapter_type}
                timecodes.append(time_dict)
            else:
                con.print("[bold yellow]WARNING:[/] A timecode was skipped. A Start time failed to match")
                continue

    # Add end key based on end time of next chapter minus one second for overlap
    for i, d in enumerate(timecodes):
        if i != len(timecodes) - 1:
            try:
                d['end'] = convert_time(timecodes[i+1]['start'])
            except ValueError as e:
                con.print(f"[bold yellow]WARNING:[/] Failed to convert time for chapter {i+1}: {e}")
                # Use the start time of next chapter as-is
                d['end'] = timecodes[i+1]['start']

    if timecodes:
        return timecodes
    else:
        con.print('[bold red]ERROR:[/] Timecodes list cannot be empty. Exiting...')
        sys.exit(8)


def verify_count(audiobook_path: Path, timecodes: list[dict]) -> None:
    """Verify that the expected number of files were generated.

    Compares the number of files split from the audiobook to ensure it matches the length of the generated
    timecodes. Checks for files with the same extension as the input file.

    :param audiobook_path: Path to audiobook file
    :param timecodes: List of dictionaries containing chapter type, start, and end times
    """
    # Count files with same extension as input (excluding the original file)
    file_ext = audiobook_path.suffix.lower()
    pattern = f'*{file_ext}'
    file_count = sum(1 for x in audiobook_path.parent.glob(pattern) if x.stem != audiobook_path.stem)
    expected = len(timecodes)

    if file_count >= expected:
        con.print(f"[bold green]SUCCESS![/] Audiobook split into {file_count} files\n")
    else:
        con.print(
            f"[bold yellow]WARNING:[/] {file_count} files were generated "
            f"which is less than the expected {expected}\n"
        )


def write_cue_file(timecodes: list[dict], cue_path: Path, audiobook_stem: str) -> bool:
    """Write audiobook timecodes to a cue file.

    Cue files can be created using the `-write_cue_file`/`-wc` argument. This provides the user with an
    easy interface for adding, modifying, or deleting chapter names, start, and end timecodes, which is
    useful when the ML speech-to-text misses or inaccurately labels a section.

    :param timecodes: Parsed timecodes to be written to the cue file
    :param cue_path: Path to cue file
    :param audiobook_stem: Stem name of the audiobook file
    :return: Boolean success/failure flag
    """
    try:
        with open(cue_path, 'x', encoding='utf-8') as fp:
            fp.write(f'FILE "{audiobook_stem}.mp3" MP3\n')
            for i, time in enumerate(timecodes, start=1):
                fp.writelines([
                    f"TRACK {i} AUDIO\n",
                    f'  TITLE\t"{time["chapter_type"]}"\n',
                    f"  START\t{time['start']}\n"
                ])
                if i != len(timecodes):
                    fp.write(f"  END\t\t{time['end']}\n")
        return True

    except OSError as e:
        con.print(f"[bold red]ERROR:[/] Failed to write cue file: {e}")
        # Delete cue file to prevent parsing error if partially written
        if cue_path.exists():
            try:
                cue_path.unlink()
            except OSError:
                pass
        return False


def read_cue_file(cue_path: Path) -> Optional[list[dict]]:
    """Read audiobook timecodes from a cue file.

    Cue files can be created using the `-write_cue_file` argument. After creation, the cue file is
    used exclusively for reading timecodes unless an error occurs or the file is moved/renamed/deleted.

    :param cue_path: Path to cue file
    :return: List of timecodes in dictionary form, or None if parsing fails
    """
    timecodes = []
    time_dict = {}

    try:
        with open(cue_path, 'r', encoding='utf-8') as fp:
            content = fp.readlines()
    except (OSError, UnicodeDecodeError) as e:
        con.print(f"[bold red]ERROR:[/] Failed to read cue file: {e}")
        return None

    content = [l.strip('\n') for l in content]

    for i, line in enumerate(content[1:], start=1):
        try:
            if 'TITLE' in line:
                if match := re.search(r'TITLE\t"(.*)"', line):
                    time_dict['chapter_type'] = match[1]
            if 'START' in line:
                if match := re.search(r'START\t(.+)', line):
                    time_dict['start'] = match[1]
            if 'END' in line and i < len(content):
                if match := re.search(r'END\t+(.+)', line):
                    time_dict['end'] = match[1]

        except (ValueError, IndexError) as e:
            con.print(f"[bold red]ERROR:[/] Failed to match line {i}: {e}. Returning...")
            return None

        # Check if we've completed a track entry
        if i < len(content) and 'TRACK' in content[i] and time_dict:
            timecodes.append(time_dict)
            time_dict = {}
        elif line == content[-1] and time_dict:
            timecodes.append(time_dict)

    if timecodes:
        return timecodes
    else:
        con.print(
            "[bold red]ERROR:[/] Timecodes read from cue file cannot be empty. "
            "Timecodes will be parsed normally until the error is corrected."
        )
        return None


def main():
    """
    Main driver function.
    """
    print("\n\n")
    con.rule("[cyan]Starting script[/cyan]")
    print("\n")
    con.print("[magenta]Preparing chapterfying magic[/magenta] :zap:...")
    print("\n")

    # Check python version
    if not sys.version_info >= (3, 10, 0):
        con.print("[bold red]CRITICAL:[/] Python version must be 3.10.0 or greater to run this script\n")
        sys.exit(20)

    # Destructure tuple
    audiobook_file, in_metadata, lang, model_name, model_type, cue_file, ffmpeg, use_existing_chapters = parse_args()

    # Check supported file formats
    supported_formats = ['.mp3', '.m4b', '.m4a']
    file_ext = audiobook_file.suffix.lower()

    if file_ext not in supported_formats:
        con.print(f"[bold red]ERROR:[/] Unsupported format: {file_ext}")
        con.print(f"[yellow]Supported formats:[/] {', '.join(supported_formats)}")
        sys.exit(9)

    # Try to extract existing chapters from M4B/M4A files first
    if file_ext in ['.m4b', '.m4a']:
        con.print(f"[cyan]M4B/M4A file detected:[/] {audiobook_file.name}")
        con.print("[magenta]Checking for existing chapter markers...[/]")

        try:
            from m4b_support import get_m4b_chapters, get_m4b_metadata

            # Try to extract existing chapters
            existing_chapters = get_m4b_chapters(audiobook_file, ffmpeg)

            if existing_chapters:
                con.print(f"[bold green]SUCCESS![/] Found {len(existing_chapters)} embedded chapters")
                print("\n")
                timecodes = existing_chapters

                # Also extract M4B metadata
                m4b_metadata = get_m4b_metadata(audiobook_file)
                if m4b_metadata:
                    con.print("[magenta]Merging M4B metadata...[/]")
                    parsed_metadata = m4b_metadata
                    if in_metadata:
                        parsed_metadata |= in_metadata

                # Skip transcription, go directly to printing chapters
                print_table(timecodes)
                print("\n")

                # Determine whether to use existing chapters
                if use_existing_chapters:
                    # Flag set - use existing chapters without prompting
                    con.print("[cyan]Using existing chapters (--use-existing-chapters flag set)[/]")
                    choice = "1"
                elif not sys.stdin.isatty():
                    # Running non-interactively - auto-select existing chapters
                    con.print("[cyan]Non-interactive mode detected - using existing chapters[/]")
                    choice = "1"
                else:
                    # Interactive mode - ask user
                    con.print("[yellow]M4B file already has chapters. Options:[/]")
                    con.print("  1. Use existing chapters (fast, recommended)")
                    con.print("  2. Re-detect chapters with ML (slow, may find different breaks)")
                    choice = input("\nChoice [1/2] (default: 1): ").strip() or "1"

                if choice == "1":
                    # Use existing chapters - skip to file splitting
                    con.rule("[cyan]Using Existing M4B Chapters[/cyan]")
                    print("\n")
                else:
                    # Continue with ML detection
                    con.print("[yellow]Continuing with ML chapter detection...[/]")
                    print("\n")
                    timecodes = None  # Reset to trigger detection
            else:
                con.print("[yellow]No embedded chapters found - will use ML detection[/]")
                print("\n")
                timecodes = None
        except ImportError:
            con.print("[yellow]m4b_support module not found - using ML detection[/]")
            print("\n")
            timecodes = None
        except Exception as e:
            con.print(f"[yellow]Could not extract M4B chapters: {e}[/]")
            con.print("[yellow]Falling back to ML detection[/]")
            print("\n")
            timecodes = None
    else:
        timecodes = None

    # Extract metadata from input file (skip if already extracted from M4B)
    if file_ext in ['.m4b', '.m4a'] and 'parsed_metadata' in locals() and parsed_metadata:
        # Already extracted from M4B
        con.rule("[cyan]Using M4B Metadata[/cyan]")
        print("\n")
    else:
        con.rule("[cyan]Extracting metadata[/cyan]")
        print("\n")
        parsed_metadata = extract_metadata(audiobook_file, ffmpeg)

    # Combine the dicts, overwriting existing keys with user values if passed
    if parsed_metadata and in_metadata:
        con.print("[magenta]Merging extracted and user metadata[/magenta]...")
        print("\n")
        parsed_metadata |= in_metadata
    # This should never hit, as genre has a default value in argparse
    elif not in_metadata and not parsed_metadata:
        con.print("[bold yellow]WARNING:[/] No metadata to append. What a shame")
        print("\n")
    # No metadata was found in file, using only argparse defaults
    elif in_metadata and not parsed_metadata:
        parsed_metadata = in_metadata
        print("\n")

    con.print(Panel(Pretty(parsed_metadata), title="ID3 Metadata"))
    print("\n")

    # Search for existing cover art
    con.rule("[cyan]Discovering Cover Art[/cyan]")
    print("\n")

    if not parsed_metadata.get('cover_art'):
        con.print("[magenta]Perusing for cover art in source[/magenta]...")
        cover_art = extract_coverart(audiobook_file, ffmpeg)
    else:
        cover_art_path = parsed_metadata['cover_art']
        if isinstance(cover_art_path, Path) and cover_art_path.exists():
            con.print("[bold green]SUCCESS![/] Cover art is...covered!")
            print("\n")
            cover_art = cover_art_path
        else:
            con.print("[bold yellow]WARNING:[/] Cover art path does not exist")
            cover_art = None

    # Download model if option selected
    if model_name and lang:
        con.rule(f"[cyan]Downloading '{lang} ({model_type})' Model[/cyan]")
        print("\n")
        con.print("[magenta]Preparing download...[/magenta]")
        print("\n")
        download_model(model_name)

    # Generate timecodes from audio file (skip if already have from M4B)
    if 'timecodes' not in locals() or timecodes is None:
        con.rule("[cyan]Generating Timecodes[/cyan]")
        print("\n")

        if model_type == 'small':
            message = "[magenta]Sit tight, this might take a while[/magenta]..."
        else:
            message = "[magenta]Sit tight, this might take a [u]long[/u] while[/magenta]..."

        with con.status(message, spinner='pong'):
            timecodes_file = generate_timecodes(audiobook_file, lang, model_type)

        # If cue file exists, read timecodes from file
        if cue_file and cue_file.exists():
            con.rule("[cyan]Reading Cue File[/cyan]")
            print("\n")

            if (cue_timecodes := read_cue_file(cue_file)) is not None:
                con.print("[bold green]SUCCESS![/] Timecodes parsed from cue file")
                timecodes = cue_timecodes
            else:
                timecodes = None
        else:
            timecodes = None

        # If timecodes not parsed from cue file, parse from srt
        if not timecodes:
            # Open file and parse timecodes
            try:
                with open(timecodes_file, 'r', encoding='utf-8') as fp:
                    file_lines = fp.readlines()
            except (OSError, UnicodeDecodeError) as e:
                con.print(f"[bold red]ERROR:[/] Failed to read timecodes file: {e}")
                sys.exit(10)

            con.rule("[cyan]Parsing Timecodes[/cyan]")
            print("\n")

            timecodes = parse_timecodes(file_lines, lang)
            con.print("[bold green]SUCCESS![/] Timecodes parsed")

        # Print timecodes table
        print("\n")
        print_table(timecodes)
        print("\n")
    else:
        # Already have timecodes from M4B
        con.print("[cyan]Using timecodes from M4B file[/cyan]")
        print("\n")

    # Generate cue file if selected and one doesn't already exist
    con.rule("[cyan]Writing Cue File[/cyan]")
    print("\n")

    if cue_file and not cue_file.exists():
        if write_cue_file(timecodes, cue_file, audiobook_file.stem):
            con.print("[bold green]SUCCESS![/] Cue file created")
    elif cue_file and cue_file.exists():
        con.print(
            "[yellow]NOTE:[/] An existing cue file was found. Move, delete, or rename it to generate a new one"
        )
    else:
        con.print("[yellow]NOTE:[/] Nothing to write")
    print("\n")

    # Split the file
    con.rule("[cyan]Chapterizing File[/cyan]")
    print("\n")
    split_file(audiobook_file, timecodes, parsed_metadata, cover_art, ffmpeg)

    # Count the generated files and compare to timecode dict to ensure they match
    verify_count(audiobook_file, timecodes)


if __name__ == '__main__':
    main()
