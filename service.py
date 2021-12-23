import ast
import datetime
import io
import logging
import os
import re
import unicodedata

from http import cookies
from logging.config import dictConfig
from typing import Any, Dict, List, Literal, Union, Tuple

import numpy as np
import requests
import zipfile

import crowdnalysis as cs
import flask

from flask import Flask, request, send_file
from flask_cors import CORS, cross_origin
from werkzeug.utils import safe_join


class ARG:
    """Request argument names"""
    PYBOSSA_API = "pbapi"
    OUTPUT_FORMAT = "format"
    CONSENSUS_MODEL = "model"


class ARG_DEFAULT:
    """Default values for request args"""
    OUTPUT_FORMAT = "csv"
    CONSENSUS_MODEL = "DawidSkene"


LOG_LEVEL = logging.DEBUG
DATA = Literal["task", "task_run", "result"]
FORMAT = Literal["csv", "json"]
INFO_ONLY_EXT = "_info_only"
TEMP_DIR = safe_join("./", ".tmp/")
TASK_KEY = "id"
CONSENSUS_COL = "consensus"
SEP = ","

# Configure the logs for Flask
dictConfig({
    "version": 1,
    "formatters": {"default": {
        "format": "[%(asctime)s] %(levelname)s: %(message)s",
    }},
    "handlers": {"wsgi": {
        "class": "logging.StreamHandler",
        "stream": "ext://flask.logging.wsgi_errors_stream",
        "formatter": "default"
    }},
    "root": {
        "level": "INFO",
        "handlers": ["wsgi"]
    }
})

# Define FLASK APP
app = Flask(__name__)
app.logger.setLevel(LOG_LEVEL)

# Allow cross-origin resource sharing (CORS)
CORS_RESOURCES = {r"/api/*": {"origins": "*",
                              "allow_headers": ["Content-Type",
                                                "Authorization"],
                              "max_age": 21600,
                              "methods": "GET"
                              }}
cors = CORS(app, resources=CORS_RESOURCES)  # Allow cross-domain requests


class UnexpectedFileError(Exception):
    """Raised when an unexpected file is received from Pybossa API"""
    pass


def _import_data_from_pybossa(api_url: str, data_type: DATA, format_: FORMAT, **kwargs) -> Tuple[zipfile.ZipFile,
                                                                                                 requests.Response]:
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
    app.logger.debug(f"I am about to make a request to the Pybossa API for {data_type}s")
    response = requests.get(api_url, params=params, allow_redirects=True, **kwargs)
    app.logger.debug("Pybossa API response.status_code for {}s: {}".format(data_type, response.status_code))
    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    return zip_file, response


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
    app.logger.debug(f"I am about to make a request to the Pybossa API for the project info")
    response = requests.get(api_url, allow_redirects=True, **kwargs)
    app.logger.debug("Pybossa API response.status_code for Project Info: {}".format(response.status_code))
    resp_json = response.json()
    task_presenter = resp_json[0]["info"]["task_presenter"]
    # Extract related substring
    qs_str = re.search(r'(?<=questions":)(.*)(?=],\s*"answers)', task_presenter).group(0) + "]"
    qs_list = ast.literal_eval(qs_str)
    assert isinstance(qs_list, list)
    QnAs = {}
    for d in qs_list:
        assert isinstance(d, dict)
        assert sorted(d.keys()) == ["answers", "question"]
        QnAs[d["question"]] = d["answers"]
    app.logger.debug(f"QnAs: {QnAs}")
    return QnAs


def get_project_info_api_url(tasks_api: str) -> Tuple[str, str]:
    """Build the API URL for the project out of the tasks API URL.

    Args:
        tasks_api: The url passed to the service by the Export Button on C3S frontend

    Returns:
        Returns the 2-tuple of URL with params to be used in GET and the project name.

    """
    base = re.match(r"(.+)project", tasks_api).group(1)  # e.g. "http://localhost:20004/
    project_name = re.search("(?<=project/)(.*)(?=/tasks)", tasks_api).group(1)
    info_api = f"{base}api/project?name={project_name}"
    return info_api, project_name


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


def file_path(fname:str, dir_=None) -> str:
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
            app.logger.debug(f"Deleted {fpath}")


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
        app.logger.error("More than two files received from Pybossa: {}".format(str(zip_members)))
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
    app.logger.debug(f"Extracted {zip_members} to {extract_to}.")

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


def import_result_files(api_url: str, extract_to: str, format_: FORMAT, **kwargs) -> Tuple[List[str], requests.Response]:
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
    app.logger.debug(f"Extracted {zip_members} to {extract_to}.")
    result_files = [file_path(fname, extract_to) for fname in zip_members]
    return result_files, response


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
    return zip_file, zip_buffer


def service_response(pybossa_api_resp: requests.Response, zip_buffer: io.BytesIO) -> flask.Response:
    """Prepare the crowdnalysis-service response.

    Args:
        pybossa_api_resp: The response object received from Pybossa API
        zip_buffer: The zip bundle to be sent to the caller

    Returns:
        A response object .

    """
    # Send file to the user as an attachment
    resp = send_file(
        zip_buffer,
        mimetype="application/octet-stream",  # pybossa_api_resp.headers["content-type"],
        as_attachment=False  # C3S deals with downloading the content as a zip attachment
    )
    # Add essential response headers
    resp.headers.add("Access-Control-Allow-Credentials", "true")
    # Allow all clients access the response. If you do not want this, use a whitelist of allowed origin(s).
    # resp.headers.add("Access-Control-Allow-Origin", flask_request.environ.get("HTTP_ORIGIN", "localhost"))
    # resp.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
    # resp.headers.add("Access-Control-Allow-Headers", "Content-Type")
    for h in ["Connection"]:  # "ETag", "Expires", "Last-Modified", "Cache-Control", "Set-Cookie", "Vary"]:
        if h in pybossa_api_resp.headers:
            if h in resp.headers:
                resp.headers[h] = pybossa_api_resp.headers.get(h)
            else:
                resp.headers.add(h, pybossa_api_resp.headers.get(h))
    return resp


def compute_consensuses(questions: List[str], task_info_only: str, task: str, task_run: str, task_key: str, model: str,
                        dir_=None, sep=SEP) -> Tuple[Dict[str, np.ndarray], cs.data.Data]:
    """Compute the consensus for each question.

    Args:
        questions: Questions asked to the crowd
        task_info_only: File name/path
        task: File name/path
        task_run: File name/path
        task_key: task id in the "task_run" file
        model: consensus model to be used, see `cs.factory.Factory.list_registered_algorithms()`
        dir_: Optional. If given, files are searched under this directory.
        sep: Separator for the CSV file.

    Returns:
        A dictionary of consensus for each question

    """
    data_ = None

    def _preprocess(df):
        """Rename info_i columns in dataframe -> info_<question_i>"""
        df = df.rename(columns={f"info_{ix}": q for ix, q in enumerate(questions)})
        return df

    try:
        # Create a crowdnalysis Data object
        data_ = cs.data.Data.from_pybossa(
            file_path(task_run, dir_),
            questions=questions,
            data_src="CS Project Builder",
            preprocess=_preprocess,
            # task_ids=task_ids,
            # categories=categories,
            task_info_file=file_path(task_info_only, dir_),
            task_file=file_path(task, dir_),
            field_task_key=task_key,
            # other_columns=other_columns,
            delimiter=sep)
        app.logger.debug("crowdnalysis.data.Data object created successfully.")
        app.logger.debug(f"Data.questions: {data_.questions}")
    except Exception as err:
        app.logger.error("Error in creating crowdnalysis.data.Data: {}".format(err))
        questions = ["N/A"]
    try:
        m = cs.factory.Factory.make(model)
        # Compute consensus for each question
        consensuses, _ = m.fit_and_compute_consensuses_from_data(d=data_, questions=questions)
        app.logger.info(f"Consensuses computed successfully for the questions: {questions}")
    except Exception as err:
        app.logger.error("Error in computing consensus: {}".format(err))
        consensuses = {}
    return consensuses, data_


def export_consensuses_to_files(format_: FORMAT, data_: cs.data.Data, consensuses: Dict[str, np.ndarray],
                                project_name: str, dir_: str = None, sep=SEP) -> List[str]:
    """ Export consensus for each question to a separate CSV file.

    Returns:
        Paths to the CSV files.

    """
    output_files = []
    for question, consensus in consensuses.items():
        df = cs.visualization.consensus_as_df(data_, question, consensus)
        df.index.name = TASK_KEY
        app.logger.debug(f"Consensus for {question}:\n{df}")
        fname = "{p}_consensus_{q}.{f}".format(p=slugify(project_name), q=slugify(question), f=format_.lower())
        fpath = file_path(fname, dir_)
        clean_files(fpath)
        if format_ == "csv":
            df.to_csv(fpath, sep=sep, index=True, header=True)
        else:  # json
            df.to_json(fpath, orient="index", indent=4)
        output_files.append(fpath)
        app.logger.debug(f"Consensus for {question} written into {fpath}.")
    return output_files


def prep_cookies(cookies_raw: str) -> Dict:
    """Convert cookies string to a dictionary of key-value pairs.

    Args:
        cookies_raw: Request cookies

    Returns:
        A dictionary of morsel values.

    """
    sc = cookies.SimpleCookie()
    sc.load(cookies_raw)
    cookies_dict = {}
    for k, morsel in sc.items():
        cookies_dict[k] = morsel.value
    return cookies_dict


@app.route("/api/")
@cross_origin()
def main():
    app.logger.info("{0} Service call {0}\n{1}".format("-" * 30, datetime.datetime.now()))
    app.logger.info("HTTP_ORIGIN: {}".format(request.environ.get("HTTP_ORIGIN", "localhost")))
    app.logger.info("URL: {}".format(request.url))
    # Prepare cookies to be used for authentication on Pybossa
    req_cookies = prep_cookies(request.headers.get("Cookie"))
    # Get the Pybossa API and other arguments from the request URL
    pbapi_url = request.args.get(ARG.PYBOSSA_API)
    consensus_model = request.args.get(ARG.CONSENSUS_MODEL, default=ARG_DEFAULT.CONSENSUS_MODEL)
    assert consensus_model in cs.factory.Factory.list_registered_algorithms()
    output_format = request.args.get(ARG.OUTPUT_FORMAT, default=ARG_DEFAULT.OUTPUT_FORMAT)
    assert output_format in FORMAT.__args__
    # Import task* files
    task_info_only, task, task_run_info_only, task_run, _ = import_task_files(api_url=pbapi_url, extract_to=TEMP_DIR,
                                                                              cookies=req_cookies)
    # Import 'result' files
    result_files, pybossa_api_response = import_result_files(api_url=pbapi_url, extract_to=TEMP_DIR,
                                                             format_=output_format, cookies=req_cookies)
    # Get questions and answers configured for the project
    info_api, project_name = get_project_info_api_url(pbapi_url)
    QnAs = import_pybossa_project_qa(info_api, cookies=req_cookies)
    # Compute the consensus for each question
    questions = list(QnAs.keys())
    consensuses, data_ = compute_consensuses(questions, task_info_only, task, task_run, task_key=TASK_KEY,
                                             model=consensus_model)
    # Export consensuses to CSV/JSON
    consensus_files = export_consensuses_to_files(output_format, data_, consensuses, project_name, TEMP_DIR, sep=SEP)
    # Make new zip for the result files
    _, zip_buffer = make_zip(files=result_files + consensus_files)
    # Prepare the service response as zip
    response = service_response(pybossa_api_resp=pybossa_api_response, zip_buffer=zip_buffer)
    # Clean files upon exit
    clean_files([task_info_only, task, task_run_info_only, task_run] + result_files + consensus_files)
    # Return the response
    return response
