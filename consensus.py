import io
import os

import numpy as np
import requests
import zipfile

import crowdnalysis as cs
import flask
import pandas as pd

from typing import List, Literal, Union, Tuple
from flask import Flask, request, send_file
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


DATA = Literal["task", "task_run", "result"]
FORMAT = Literal["csv", "json"]
INFO_ONLY_EXT = "_info_only"
TEMP_DIR = safe_join("./", ".tmp/")
TASK_KEY = "task_id"
CONSENSUS_COL = "consensus"


app = Flask(__name__)


class UnexpectedFileError(Exception):
    """Raised when an unexpected file is received from Pybossa API"""
    pass


def _export_data_from_pybossa(api_url: str, data_type: DATA, **kwargs) -> Tuple[zipfile.ZipFile, requests.Response]:
    """Get exported task files

    Args:
        api_url: Pybossa API URL
        data_type: Data type to be exported
        **kwargs: Passed over to the `requests.get()` method
    Returns:
        2-tuple of (Zip file, `requests.Response`) returned from the Pybossa API.
    """
    # Call Pybossa API
    params = {
        "type": data_type,
        "format": "csv"  # crowdnalysis expects CSV
    }
    response = requests.get(api_url, params=params, allow_redirects=True, **kwargs)
    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    return zip_file, response


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
    """

    Args:
        dir_: Path to the given `files`
        files: A single or a list of file names

    Returns:

    """
    if not isinstance(files, list):
        files = [files]
    for fname in files:
        fpath = file_path(fname, dir_)
        if os.path.exists(fpath):
            os.remove(fpath)


def _extract_files_in_zip(zip_file: zipfile.ZipFile, extract_to: str) -> Tuple[str, str]:
    """

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

    return (os.path.join(extract_to, zip_members[idx_info_only_file]),
            os.path.join(extract_to, zip_members[1 - idx_info_only_file]))


def export_task_files(api_url: str, extract_to: str) -> Tuple[str, str, str, str]:
    """

    Args:
        api_url: Pybossa API URL
        extract_to: Extraction path for the task files

    Returns:
        4-Tuple of full paths to (task_info_only, task, task_run_info_only, task_run) files fetched from Pybossa
    """
    # Get the exported "task" zip
    zip_file, _ = _export_data_from_pybossa(api_url=api_url, data_type="task")
    task_info_only, task = _extract_files_in_zip(zip_file, extract_to)
    # Get the exported "task_run" zip
    zip_file, _ = _export_data_from_pybossa(api_url=api_url, data_type="task_run")
    task_run_info_only, task_run = _extract_files_in_zip(zip_file, extract_to)

    return task_info_only, task, task_run_info_only, task_run


def export_result_file(api_url: str, extract_to: str) -> Tuple[str, str]:
    """

    Args:
        api_url: Pybossa API URL
        extract_to: Extraction path for the result file

    Returns:
        2-Tuple of full paths to (result_info_only, result) fıles fetched from Pybossa
    """
    # Get the exported "result" zip
    zip_file, _ = _export_data_from_pybossa(api_url, data_type="result")
    result_info_only, result = _extract_files_in_zip(zip_file, extract_to)
    return result_info_only, result


def make_zip(files: Union[str, List[str]], dir_: str = None, zip_path: str = None) -> Tuple[zipfile.ZipFile,
                                                                                            io.BytesIO]:
    """

    Args:
        files: A single or a list of file names/paths to be zipped
        dir_: Optional. If given, `files` are looked for under this directory.
        zip_path: Optional. If given, a zip file is actually written to the disk at this full path. In this case,
            the path should include the file name too.

    Returns:
        2-Tuple of the ZipFile object and its contents as bytes. The latter is sent to the C3S for downloading.
    """
    # Make the zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for fname in files:
            fpath = file_path(fname, dir_)
            zip_file.write(fpath, arcname=os.path.basename(fname))
    if zip_path is not None:
        # Remove existing file, just in case
        clean_files(zip_path)
        # Actually write the zip to the disk
        with open(zip_path, "wb") as f:
            f.write(zip_buffer.getvalue())
    zip_buffer.seek(0)  # This line is important before sending the content
    return zip_file, zip_buffer


def return_zip(flask_request: flask.Request, zip_buffer: io.BytesIO) -> flask.Response:
    """"""
    # Send file to the user as an attachment
    resp = send_file(
        zip_buffer,
        mimetype="application/octet-stream",  # pbapi_resp.headers["content-type"],
        # as_attachment=False)  # C3S, deals with downloading the content as a zip attachment
        as_attachment=True,  # In case, the API is called by other means...
        attachment_filename="result.zip")
    # Add essential response headers
    resp.headers.add("Access-Control-Allow-Credentials", "true")
    resp.headers.add("Access-Control-Allow-Origin", flask_request.environ.get("HTTP_ORIGIN", "localhost"))

    return resp


def compute_consensus(task_info_only: str, task: str, task_run: str, task_key: str, model: str,
                      dir_=None, sep=",") -> Tuple[List[str], List[cs.consensus.DiscreteConsensus]]:
    """

    Args:
        task_info_only:
        task:
        task_run:
        task_key:
        model:
        dir_:
        sep:

    Returns:
        A 2-tuple of questions and consensuses for them
    """
    # Prepare data
    data_ = None
    try:
        data_ = cs.data.Data.from_pybossa(
            file_path(task_run, dir_),
            questions=None,  # This will be automatically extracted by the cs
            data_src="CS Project Builder",
            # preprocess=preprocess if preprocess else self.preprocess,
            # task_ids=task_ids,
            # categories=categories,
            task_info_file=file_path(task_info_only, dir_),
            task_file=file_path(task, dir_),
            field_task_key=task_key,
            # other_columns=other_columns,
            delimiter=sep)
        questions = data_.questions
    except Exception as err:
        print("Error in creating crowdnalysis.data.Data:", err)
        questions = ["N/A"]
    try:
        m = cs.factory.Factory.make(model)
        # Compute consensus for each question
        consensuses, _ = m.fit_and_compute_consensuses_from_data(d=data_, questions=questions)
    except Exception as err:
        print("Error in computing consensus:", err)
        consensuses = [None] * len(questions)
    print("questions, consensuses:", questions, consensuses)
    return questions, consensuses


def add_consensus_to_results(result: str, consensuses: List[np.ndarray], questions: List[str], dir_=None, sep=","):
    """
    Extends the result.csv file one column per the consensus of each question. The same file is overwritten.

    Args:
        consensuses:
        questions:
        result: Full path to the result.csv file
        dir_:
        sep:

    Returns:
        None.
    """
    try:
        result_path = file_path(result, dir_)
        df_result = pd.read_csv(result_path)
        for ix, consensus in enumerate(consensuses):
            if consensus is not None:
                best = np.argmax(consensus, axis=1)
                best_lbl = best.apply(lambda x: questions[x], axis=0)
            else:
                best_lbl = np.full((df_result.shape[0]), np.nan)
            df_result[questions[ix]] = df_result[CONSENSUS_COL + "_" + questions[ix]] = best_lbl
        print("df_result.cols:", list(df_result.columns))
        df_result.to_csv(result_path, sep=sep)
    except Exception as err:
        print("Error in adding consensus column(s) to the result file:", err)


@app.route("/api/")
def index():
    # print("HTTP_ORIGIN:", request.environ.get("HTTP_ORIGIN", "localhost"))
    # print("request.url:", request.url)
    # Get the Pybossa API  and other arguments from the request URL
    pbapi_url = request.args.get(ARG.PYBOSSA_API)
    consensus_model = request.args.get(ARG.CONSENSUS_MODEL, default=ARG_DEFAULT.CONSENSUS_MODEL)
    assert consensus_model in cs.factory.Factory.list_registered_algorithms()
    output_format = request.args.get(ARG.OUTPUT_FORMAT, default=ARG_DEFAULT.OUTPUT_FORMAT)
    assert output_format in FORMAT.__args__
    # print("pbapi:", pbapi_url)
    # Export task* files
    task_info_only, task, task_run_info_only, task_run = export_task_files(api_url=pbapi_url, extract_to=TEMP_DIR)
    # Export 'result' file
    result_info_only, result = export_result_file(api_url=pbapi_url, extract_to=TEMP_DIR)
    # Compute the consensus
    # TODO (OM, 20211213): Would the task_key change for some project?
    questions, consensuses = compute_consensus(task_info_only, task, task_run, task_key=TASK_KEY, model=consensus_model)
    # Add consensus column to the result file
    add_consensus_to_results(result, consensuses, questions)
    # Make new zip for the result file
    _, zip_buffer = make_zip(files=[result_info_only, result])
    # Return zip
    response = return_zip(flask_request=request, zip_buffer=zip_buffer)
    # Clean files upon exit
    clean_files([task_info_only, task, task_run_info_only, task_run, result_info_only, result])
    # Return the response
    return response

