import ast
import datetime
import io
import os
import re
import unicodedata

from http import cookies
from typing import Any, Dict, List, Literal, Union, Tuple

import numpy as np
import requests
import zipfile

import crowdnalysis as cs
import flask
import pandas as pd


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


DATA = Literal["task", "task_run", "result"]
FORMAT = Literal["csv", "json"]
INFO_ONLY_EXT = "_info_only"
TEMP_DIR = safe_join("./", ".tmp/")
# TASK_ID = "task_id"
TASK_KEY = "id"
CONSENSUS_COL = "consensus"
SEP = ","


app = Flask(__name__)
# CORS_RESOURCES = {r"/zapi/*": {"origins": "*",
#                               "allow_headers": ['Content-Type',
#                                                 'Authorization'],
#                               "methods": "*"
#                               }}
CORS_RESOURCES = {r"/api/*": {"origins": "*",
                              "allow_headers": ['Content-Type',
                                                'Authorization'],
                              "max_age": 21600
                              }}
cors = CORS(app, resources=CORS_RESOURCES)  # Allow cross-domain requests

# headers_dict = None


class UnexpectedFileError(Exception):
    """Raised when an unexpected file is received from Pybossa API"""
    pass


def _import_data_from_pybossa(api_url: str, data_type: DATA, **kwargs) -> Tuple[zipfile.ZipFile, requests.Response]:
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
    print(f"I am about to make a request to the Pybossa API for {data_type}s")
    # print("api_url:", api_url, "\nparams:", params, "\nkwargs:\n", kwargs)
    response = requests.get(api_url, params=params, allow_redirects=True, **kwargs)
    print("Pybossa API response.status_code:", response.status_code)
    # print("Pybossa API response.headers:\n", response.headers)
    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    return zip_file, response


def import_pybossa_project_QnAs(api_url, **kwargs) -> Dict[str, List[Any]]:
    # Call Pybossa API
    response = requests.get(api_url, allow_redirects=True, **kwargs)
    print("info_api status code:", response.status_code)
    # print("info:", response.json())
    resp_json = response.json()
    task_presenter = resp_json[0]["info"]["task_presenter"]
    # print("task_presenter:", task_presenter)
    qs_str = re.search(r'(?<=questions":)(.*)(?=],\s*"answers)', task_presenter).group(0) + "]"
    print("Qs:", qs_str)  # e.g.  [{"question":"Relevant","answers":["Yes", "No"]}]
    qs_list = ast.literal_eval(qs_str)
    assert isinstance(qs_list, list)
    QnAs = {}
    for d in qs_list:
        assert isinstance(d, dict)
        assert sorted(d.keys()) == ["answers", "question"]
        QnAs[d["question"]] = d["answers"]
    print("QnAs:", QnAs)
    return QnAs


def get_project_info_api_url(tasks_api: str) -> Tuple[str, str]:
    """Builds the API URL for the project out of the tasks API URL.

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

    Ref: https://github.com/django/django/blob/master/django/utils/text.py
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


def import_task_files(api_url: str, extract_to: str, **kwargs) -> Tuple[str, str, str, str, requests.Response]:
    """

    Args:
        api_url: Pybossa API URL
        extract_to: Extraction path for the task files
        **kwargs: Passed over to the `_import_data_from_pybossa()`

    Returns:
        5-Tuple of full paths to (task_info_only, task, task_run_info_only, task_run) files fetched from Pybossa
    """
    # Get the exported "task" zip
    zip_file, _ = _import_data_from_pybossa(api_url=api_url, data_type="task", **kwargs)
    task_info_only, task = _extract_files_in_zip(zip_file, extract_to)
    # Get the exported "task_run" zip
    zip_file, response = _import_data_from_pybossa(api_url=api_url, data_type="task_run", **kwargs)
    task_run_info_only, task_run = _extract_files_in_zip(zip_file, extract_to)

    return task_info_only, task, task_run_info_only, task_run, response


def import_result_file(api_url: str, extract_to: str, **kwargs) -> Tuple[str, str, requests.Response]:
    """

    Args:
        api_url: Pybossa API URL
        extract_to: Extraction path for the result file
        **kwargs: Passed over to the `_import_data_from_pybossa()`

    Returns:
        3-Tuple of full paths to (result_info_only, result) fıles fetched from Pybossa
    """
    # Get the exported "result" zip
    zip_file, response = _import_data_from_pybossa(api_url, data_type="result", **kwargs)
    result_info_only, result = _extract_files_in_zip(zip_file, extract_to)
    return result_info_only, result, response


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


def service_response(flask_request: flask.Request, pybossa_api_resp, zip_buffer: io.BytesIO) -> flask.Response:
    """"""
    # Send file to the user as an attachment
    resp = send_file(
        zip_buffer,
        mimetype="application/octet-stream",  # pbapi_resp.headers["content-type"],
        # as_attachment=False)  # C3S, deals with downloading the content as a zip attachment
        as_attachment=True,  # In case, the API is called by other means...
        attachment_filename="result.zip",
    )
    # Add essential response headers
    resp.headers.add("Access-Control-Allow-Credentials", "true")
    # Allow all clients access the response. If you do not want this, use whitelist of allowed origin(s)
    # resp.headers.add("Access-Control-Allow-Origin", flask_request.environ.get("HTTP_ORIGIN", "localhost"))
    # resp.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
    # resp.headers.add("Access-Control-Allow-Headers", "Content-Type")
    # resp.headers.add("Set-Cookie", flask_request.headers.get("Cookie"))
    for h in ["Connection"]:  # "ETag", "Expires", "Last-Modified", "Cache-Control", "Set-Cookie", "Vary"]:
        if h in pybossa_api_resp.headers:
            if h in resp.headers:
                resp.headers[h] = pybossa_api_resp.headers.get(h)
            else:
                resp.headers.add(h, pybossa_api_resp.headers.get(h))

    return resp


def compute_consensuses(questions: List[str], task_info_only: str, task: str, task_run: str, task_key: str, model: str,
                        dir_=None, sep=SEP) -> Tuple[Dict[str, np.ndarray], cs.data.Data]:
    """

    Args:
        questions:
        task_info_only:
        task:
        task_run:
        task_key:
        model:
        dir_:
        sep:

    Returns:
        A dictionary of consensus for each question
    """
    # Prepare data
    data_ = None

    def _preprocess(df):
        df = df.rename(columns={f"info_{ix}": q for ix, q in enumerate(questions)})
        return df

    try:
        data_ = cs.data.Data.from_pybossa(
            file_path(task_run, dir_),
            questions=questions,  # This will be automatically extracted by the cs
            data_src="CS Project Builder",
            preprocess=_preprocess,
            # task_ids=task_ids,
            # categories=categories,
            task_info_file=file_path(task_info_only, dir_),
            task_file=file_path(task, dir_),
            field_task_key=task_key,
            # other_columns=other_columns,
            delimiter=sep)
        print("data_.questions:", data_.questions)
        print("data_.df:\n", data_.df)
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
    # consensus_dict = dict(zip(questions, consensuses))
    # print("consensus_dict:", consensus_dict)
    print("consensuses:", consensuses)
    return consensuses, data_


# def add_consensus_to_results(result: str, consensuses: List[np.ndarray], questions: List[str], dir_=None, sep=SEP):
#     """
#     Extends the result.csv file one column per the consensus of each question. The same file is overwritten.
#
#     Args:
#         consensuses:
#         questions:
#         result: Full path to the result.csv file
#         dir_:
#         sep:
#
#     Returns:
#         None.
#     """
#     try:
#         result_path = file_path(result, dir_)
#         df_result = pd.read_csv(result_path)
#         for ix, consensus in enumerate(consensuses):
#             if consensus is not None:
#                 best = np.argmax(consensus, axis=1)
#                 best_lbl = best.apply(lambda x: questions[x], axis=0)
#             else:
#                 best_lbl = np.full((df_result.shape[0]), np.nan)
#             df_result[questions[ix]] = df_result[CONSENSUS_COL + "_" + questions[ix]] = best_lbl
#         print("df_result.cols:", list(df_result.columns))
#         df_result.to_csv(result_path, sep=sep)
#     except Exception as err:
#         print("Error in adding consensus column(s) to the result file:", err)


def export_consesuses_to_csv(data_: cs.data.Data, consensuses: Dict[str, np.ndarray], project_name: str,
                             dir_: str = None, sep=SEP) -> List[str]:
    """
    Exports consensus for each question to a separate CSV file
    Args:
        data_:
        consensuses:
        project_name:
        dir_:
        sep:

    Returns:
        Paths to the CSV files.
    """
    csv_files = []
    for question, consensus in consensuses.items():
        df = cs.visualization.consensus_as_df(data_, question, consensus)
        df.index.name = TASK_KEY
        print(f"consensus for {question}:\n", df)
        fname = "{p}_consensus_{q}.csv".format(p=slugify(project_name), q=slugify(question))
        fpath = file_path(fname, dir_)
        clean_files(fpath)
        df.to_csv(fpath, sep=sep, index=True, header=True)
        csv_files.append(fpath)
        print(f"consensus for {question} written into {fpath}")
    return csv_files


def prep_cookies(cookies_raw: str) -> Dict:
    """

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
def index():
    print("{0} Service call {0}\n{1}".format("-" * 30, datetime.datetime.now()))
    # print("HTTP_ORIGIN:", request.environ.get("HTTP_ORIGIN", "localhost"))
    # print("request.url:", request.url)
    # print("request.headers:\n", request.headers)
    # print("request.headers.cookies:\n", request.headers.get("Cookie"))
    req_cookies = prep_cookies(request.headers.get("Cookie"))
    # req_cookies = {}
    # print("cookies:\n", req_cookies)
    # headers_dict = {"Access-Control-Allow-Credentials": "true",
    #                "Access-Control-Allow-Origin": request.environ.get("HTTP_ORIGIN", "localhost")}
    # print("headers_dict:", headers_dict)
    # Get the Pybossa API  and other arguments from the request URL
    pbapi_url = request.args.get(ARG.PYBOSSA_API)
    consensus_model = request.args.get(ARG.CONSENSUS_MODEL, default=ARG_DEFAULT.CONSENSUS_MODEL)
    assert consensus_model in cs.factory.Factory.list_registered_algorithms()
    output_format = request.args.get(ARG.OUTPUT_FORMAT, default=ARG_DEFAULT.OUTPUT_FORMAT)
    assert output_format in FORMAT.__args__
    # print("pbapi:", pbapi_url)

    # Export task* files
    task_info_only, task, task_run_info_only, task_run, _ = import_task_files(api_url=pbapi_url, extract_to=TEMP_DIR,
                                                                              cookies=req_cookies)
    # Export 'result' file
    result_info_only, result, pybossa_api_response = import_result_file(api_url=pbapi_url, extract_to=TEMP_DIR,
                                                                        cookies=req_cookies)
    # Get questions
    info_api, project_name = get_project_info_api_url(pbapi_url)
    QnAs = import_pybossa_project_QnAs(info_api, cookies=req_cookies)
    # Compute the consensus
    questions = list(QnAs.keys())
    print("questions:", questions)
    consensuses, data_ = compute_consensuses(questions, task_info_only, task, task_run, task_key=TASK_KEY,
                                             model=consensus_model)
    # Export consensuses to CSV
    csv_files = export_consesuses_to_csv(data_, consensuses, project_name, TEMP_DIR, sep=SEP)
    # Add consensus column to the result file
    # add_consensus_to_results(result, consensuses, questions)
    # Make new zip for the result file
    _, zip_buffer = make_zip(files=[result_info_only, result] + csv_files)
    # Return zip
    response = service_response(flask_request=request, pybossa_api_resp=pybossa_api_response, zip_buffer=zip_buffer)
    # Clean files upon exit
    clean_files([task_info_only, task, task_run_info_only, task_run, result_info_only, result] + csv_files)
    # Return the response
    return response
    return "OK"

