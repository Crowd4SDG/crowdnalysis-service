"""Handling files"""
import io
import os
import re
import unicodedata
import zipfile
from typing import List, Union, Tuple

from werkzeug.utils import safe_join

from app import logger


CSV_SEP = ","  # Delimiter for CSV files
TEMP_DIR = safe_join("./", ".tmp/")  # Temp files will be created here


def file_path(fname: str, dir_=None) -> str:
    """Return full path of a file.

    Args:
        fname: File name/path
        dir_: Optional. Path of a file

    Returns:
        File path.

    """
    return fname if dir_ is None else os.path.join(dir_, fname)


def clean_files(files: Union[str, List[str]], dir_: str = None):
    """Delete given file(s); silently ignore missing ones.

    Args:
        dir_: Path to the given `files`
        files: A single or a list of file names

    Returns:
        None.

    """
    if not isinstance(files, list):
        files = [files]
    for fname in files:
        fpath = file_path(fname, dir_)
        if os.path.exists(fpath):
            os.remove(fpath)
            logger.debug(f"Deleted {fpath}")


def slugify(value, allow_unicode=False):
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.

    Source: https://github.com/django/django/blob/master/django/utils/text.py

    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')


def make_zip(files: Union[str, List[str]], dir_: str = None) -> Tuple[zipfile.ZipFile, io.BytesIO]:
    """Make a zip bundle with the given files.

    Args:
        files: A single or a list of file names/paths to be zipped
        dir_: Optional. If given, `files` are searched under this directory.

    Returns:
        2-Tuple of the ZipFile object and its contents as bytes. The latter is sent to the C3S for downloading.

    """
    # Make the zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for fname in files:
            fpath = file_path(fname, dir_)
            zip_file.write(fpath, arcname=os.path.basename(fname))
    zip_buffer.seek(0)  # This line is important before sending the content
    logger.info("Zip file formed with members: {}".format([os.path.basename(f) for f in files]))
    return zip_file, zip_buffer
