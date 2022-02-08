"""Interactions with Pybossa API"""
import ast
import io
import os
import re
import zipfile
from typing import Any, Dict, List, Literal, Tuple

import requests

from app import logger
from app.files import clean_files, file_path


DATA = Literal["task", "task_run", "result"]
INFO_ONLY_EXT = "_info_only"
OUTPUT_FORMAT = Literal["csv", "json"]  # Output format for files
TASK_KEY = "id"


class UnexpectedFileError(Exception):
    """Raised when an unexpected file is received from Pybossa API"""
    pass


def docker_safe_pbapi_url(url: str) -> str:
    """Resolve 'localhost' to the internal IP address used by the host."""
    service_host = os.environ.get("PYBOSSA_API_HOST")
    if service_host:
        url = url.replace("localhost", service_host)
    else:
        logger.warning("PYBOSSA_API_HOST env variable is not defined.")
    return url


def _import_data_from_pybossa(api_url: str, data_type: DATA, format_: OUTPUT_FORMAT, **kwargs) -> \
            Tuple[zipfile.ZipFile, requests.Response]:
    """Get exported task files from Pybossa.

    Args:
        api_url: Pybossa API URL for exporting tasks
        data_type: Data type to be exported
        format_: Format of the exported files
        **kwargs: Passed over to the `requests.get()` method

    Returns:
        2-tuple of (Zip file, `requests.Response`) returned from the Pybossa API.

    """
    # Call Pybossa API
    params = {
        "type": data_type,
        "format": format_
    }
    logger.debug(f"I am about to make a request to the Pybossa API for {data_type}s")
    response = requests.get(api_url, params=params, allow_redirects=True, **kwargs)
    logger.debug("Pybossa API response.status_code for {}s: {}".format(data_type, response.status_code))
    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    return zip_file, response


def _extract_task_files_in_zip(zip_file: zipfile.ZipFile, extract_to: str) -> Tuple[str, str]:
    """Extract zip members to the given path.

    Args:
        zip_file: Zip file returned from the Pybossa API
        extract_to: Extraction path

    Returns:
        A 2-tuple of (~_info_only.csv, ~ .csv) file names in the given zip archive

    Raises:
        UnexpectedFileError: If there are not two files in the zip or base names of these two files do not match.

    """
    zip_members = zip_file.namelist()
    if len(zip_members) != 2:
        logger.error("More than two files received from Pybossa: {}".format(str(zip_members)))
        raise UnexpectedFileError("Two files expected but {} received from Pybossa API.".format(len(zip_members)))
    # Get the order of the ~_info_only, ~ files
    idx_info_only_file = 0 if INFO_ONLY_EXT in zip_members[0] else 1
    idx_info_only = zip_members[idx_info_only_file].find(INFO_ONLY_EXT)
    base_file_name = zip_members[idx_info_only_file][:idx_info_only]
    if base_file_name != zip_members[1 - idx_info_only_file].split(".")[0]:
        raise UnexpectedFileError("Base names of the files received from Pybossa API "
                                  "do not match: {}.}".format(str(zip_members)))
    # Delete the existing files with identical names, just in case.
    clean_files(zip_members, extract_to)
    # Extract the zip file
    zip_file.extractall(extract_to)
    logger.debug(f"Extracted {zip_members} to {extract_to}.")

    return (file_path(zip_members[idx_info_only_file], extract_to),
            file_path(zip_members[1 - idx_info_only_file], extract_to))


def import_task_files(api_url: str, extract_to: str, **kwargs) -> Tuple[str, str, str, str, requests.Response]:
    """Import task and task_run files of a project in CSV format.

    crowdnalysis works with CSV files.

    Args:
        api_url: Pybossa API URL passed to the service from C3S, including the project name
        extract_to: Extraction path for the task files
        **kwargs: Passed over to the `_import_data_from_pybossa()`

    Returns:
        5-Tuple of full paths to (task_info_only, task, task_run_info_only, task_run) files fetched from Pybossa
        together with the API Response object.

    """
    # Get the exported "task" zip
    zip_file, _ = _import_data_from_pybossa(api_url=api_url, data_type="task", format_="csv", **kwargs)
    task_info_only, task = _extract_task_files_in_zip(zip_file, extract_to)
    # Get the exported "task_run" zip
    zip_file, response = _import_data_from_pybossa(api_url=api_url, data_type="task_run", format_="csv", **kwargs)
    task_run_info_only, task_run = _extract_task_files_in_zip(zip_file, extract_to)

    return task_info_only, task, task_run_info_only, task_run, response


def import_result_files(api_url: str, extract_to: str, format_: OUTPUT_FORMAT, **kwargs) -> Tuple[List[str],
                                                                                                  requests.Response]:
    """Import result files of a project.

    Args:
        api_url: Pybossa API URL passed to the service from C3S, including the project name
        extract_to: Extraction path for the result file
        format_: Format of the exported files
        **kwargs: Passed over to the `_import_data_from_pybossa()`

    Returns:
        2-Tuple of list of full paths to result files fetched from Pybossa together with the API Response object

    Notes:
        Pybossa API returns a zip with two files when output format is CSV: ~result_info_only.csv, ~result.csv;
        whereas, it returns a zip with only a single file when the format is JSON: ~result.json.

    """
    # Get the exported "result" zip
    zip_file, response = _import_data_from_pybossa(api_url, data_type="result", format_=format_, **kwargs)
    # Delete the existing files with identical names, just in case.
    zip_members = zip_file.namelist()
    clean_files(zip_members, extract_to)
    # Extract the zip file
    zip_file.extractall(extract_to)
    logger.debug(f"Extracted {zip_members} to {extract_to}.")
    result_files = [file_path(fname, extract_to) for fname in zip_members]
    return result_files, response


def import_pybossa_project_qa(api_url, **kwargs) -> Dict[str, List[Any]]:
    """Extract `questions` and their possible `answers` for a project.

    Args:
        api_url: Pybossa API URL for fetching project info
        **kwargs: Passed over to the `requests.get()` method

    Returns:
        A dictionary of (question, possible answers list) key-value pairs.
        e.g. {"Relevant": ["Yes", "No"]}

    Notes:
        Q&A information was found only within the `task_presenter` configuration.
        See that template in CS Project Builder frontend.

    """
    # Call Pybossa API
    logger.debug(f"I am about to make a request to the Pybossa API for the project info")
    response = requests.get(api_url, allow_redirects=True, **kwargs)
    logger.debug("Pybossa API response.status_code for Project Info: {}".format(response.status_code))
    resp_json = response.json()
    task_presenter = resp_json[0]["info"]["task_presenter"]
    # Extract related substring
    qs_str = re.search(r'(?<=questions":)(.*)(?=],\s*"answers)', task_presenter).group(0) + "]"
    qs_list = ast.literal_eval(qs_str)
    assert isinstance(qs_list, list)
    QnA = {}
    for d in qs_list:
        assert isinstance(d, dict)
        assert sorted(d.keys()) == ["answers", "question"]
        QnA[d["question"]] = d["answers"]
    logger.debug(f"QnA: {QnA}")
    return QnA


def get_project_info_api_url(tasks_api: str) -> Tuple[str, str]:
    """Build the API URL for the project out of the tasks API URL.

    Args:
        tasks_api: The url passed to the service by the Export Button on C3S frontend

    Returns:
        Returns the 2-tuple of URL with params to be used in GET and the project short name.

    """
    base = re.match(r"(.+)project", tasks_api).group(1)  # e.g. "http://localhost:20004/
    project_short_name = re.search("(?<=project/)(.*)(?=/tasks)", tasks_api).group(1)
    info_api = f"{base}api/project?short_name={project_short_name}"
    return info_api, project_short_name
