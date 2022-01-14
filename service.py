import datetime
import io
from dataclasses import dataclass
from http import cookies
from typing import Dict, Tuple

import flask
import requests
from flask import request, send_file
from flask_cors import cross_origin, CORS

from app import create_app, logger
from app.consensus import compute_consensuses, export_consensuses_to_files, REGISTERED_ALGORITHMS
from app.files import make_zip, clean_files, TEMP_DIR, CSV_SEP
from app import pb


# Define FLASK APP
app = create_app()

# Allow cross-origin resource sharing (CORS)
CORS_RESOURCES = {r"/api/*": {"origins": "*",
                              "allow_headers": ["Content-Type",
                                                "Authorization"],
                              "max_age": 21600,
                              "methods": "GET"
                              }}
cors = CORS(app, resources=CORS_RESOURCES)  # Allow cross-domain requests


class ARG:
    """Request argument names and default values to be used as constants"""
    @dataclass
    class ReqArg:
        name: str  # name of the request arg
        default: str = None  # its default value
    PYBOSSA_API = ReqArg("pbapi")
    FORMAT = ReqArg("format", "csv")
    CONSENSUS_MODEL = ReqArg("model", "DawidSkene")


def log_service_call():
    """Prints log messages for the service call"""
    logger.info("{0} Service call {0}\n{1}".format("-" * 30, datetime.datetime.now()))
    logger.info("HTTP_ORIGIN: {}".format(request.environ.get("HTTP_ORIGIN", "localhost")))
    logger.info("URL: {}".format(request.url))


def get_request_args() -> Tuple[str, str, str]:
    """Get args from the service request

    Returns:
        A 3-tuple of (Pybossa API URL, Output file format, Consensus model).
    """
    # Get the Pybossa API and other arguments from the request URL
    pbapi_url = pb.docker_safe_pbapi_url(request.args.get(ARG.PYBOSSA_API.name))
    logger.info(f"Pybossa API URL: {pbapi_url}")
    output_format = request.args.get(ARG.FORMAT.name, default=ARG.FORMAT.default)
    assert output_format in pb.OUTPUT_FORMAT.__args__
    consensus_model = request.args.get(ARG.CONSENSUS_MODEL.name, default=ARG.CONSENSUS_MODEL.default)
    assert consensus_model in REGISTERED_ALGORITHMS
    return pbapi_url, output_format, consensus_model


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
    # Log service call
    log_service_call()
    # Get the arguments from the request URL
    pbapi_url, output_format,  consensus_model = get_request_args() 
    # Prepare cookies to be used for authentication on Pybossa
    req_cookies = prep_cookies(request.headers.get("Cookie"))
    # Import task* files
    task_info_only, task, task_run_info_only, task_run, _ = pb.import_task_files(api_url=pbapi_url, extract_to=TEMP_DIR,
                                                                                 cookies=req_cookies)
    # Import result* files
    result_files, pybossa_api_response = pb.import_result_files(api_url=pbapi_url, extract_to=TEMP_DIR,
                                                                format_=output_format, cookies=req_cookies)
    # Get questions and answers configured for the project
    info_api, project_name = pb.get_project_info_api_url(pbapi_url)
    QnA = pb.import_pybossa_project_qa(info_api, cookies=req_cookies)
    # Compute the consensus for each question
    questions = list(QnA.keys())
    consensuses, data_ = compute_consensuses(questions, task_info_only, task, task_run, task_key=pb.TASK_KEY,
                                             model=consensus_model)
    # Export consensuses to CSV/JSON
    consensus_files = export_consensuses_to_files(output_format, data_, consensuses, project_name, TEMP_DIR,
                                                  sep=CSV_SEP)
    # Make new zip for the result files
    _, zip_buffer = make_zip(files=result_files + consensus_files)
    # Prepare the service response as zip
    response = service_response(pybossa_api_resp=pybossa_api_response, zip_buffer=zip_buffer)
    # Clean files upon exit
    clean_files([task_info_only, task, task_run_info_only, task_run] + result_files + consensus_files)
    # Return the response
    return response
