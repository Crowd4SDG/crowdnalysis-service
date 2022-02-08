"""Handling consensus computation"""
from typing import Dict, List, Tuple

import crowdnalysis as cs
import numpy as np

from app import logger
from app.files import clean_files, file_path, slugify, CSV_SEP
from app.pb import OUTPUT_FORMAT, TASK_KEY


REGISTERED_ALGORITHMS = cs.factory.Factory.list_registered_algorithms()


def compute_consensuses(questions: List[str], task_info_only: str, task: str, task_run: str, task_key: str, model: str,
                        dir_=None, sep: str = CSV_SEP) -> Tuple[Dict[str, np.ndarray], cs.data.Data]:
    """Compute the consensus for each question.

    Args:
        questions: Questions asked the crowd
        task_info_only: File name/path
        task: File name/path
        task_run: File name/path
        task_key: task id in the "task_run" file
        model: consensus model to be used, see `cs.factory.Factory.list_registered_algorithms()`
        dir_: Optional. If given, files are searched under this directory.
        sep: Separator for the CSV file.

    Returns:
        A 2-tuple of:
         . a dictionary of (question, consensus) pairs, and
         . the `crowdnalysis.data.Data` object created for the annotations

    """
    data_ = None
    model_ = None
    consensuses = {}

    def _preprocess(df):
        """Rename info_<i> columns in dataframe -> <question_i>"""
        df = df.rename(columns={f"info_{ix}": q for ix, q in enumerate(questions)})
        return df

    # Create a crowdnalysis Data object
    try:
        data_ = cs.data.Data.from_pybossa(
            file_path(task_run, dir_),
            questions=questions,
            data_src="CS Project Builder",
            preprocess=_preprocess,
            task_info_file=file_path(task_info_only, dir_),
            task_file=file_path(task, dir_),
            field_task_key=task_key,
            delimiter=sep)
        logger.debug("crowdnalysis.data.Data object created successfully.")
        logger.debug(f"Data.questions: {data_.questions}")
    except Exception as err:
        logger.error("Error in creating crowdnalysis.data.Data: {}".format(err))
        questions = ["N/A"]
    # Create consensus model object
    if data_ is not None:
        try:
            model_ = cs.factory.Factory.make(model)
        except Exception as err:
            logger.error("Error in creating consensus model {}: {}".format(model, err))
    if data_ is None or model_ is None:
        logger.warning("Consensus computation cannot start.")
        return consensuses, data_
    # Compute consensus for each question
    for q in questions:
        try:
            consensuses[q], _ = model_.fit_and_compute_consensus_from_data(d=data_, question=q)
            logger.info(f"Consensus computed successfully for the question: {q}")
        except Exception as err:
            logger.error("Error in computing consensus: {}".format(err))
    return consensuses, data_


def export_consensuses_to_files(format_: OUTPUT_FORMAT, data_: cs.data.Data, consensuses: Dict[str, np.ndarray],
                                project_name: str, dir_: str = None, sep=CSV_SEP) -> List[str]:
    """ Export consensus for each question to a separate CSV file.

    Returns:
        Paths to the CSV files.

    """
    output_files = []
    for question, consensus in consensuses.items():
        df = cs.visualization.consensus_as_df(data_, question, consensus)
        df.index.name = TASK_KEY
        logger.debug(f"Consensus for {question}:\n{df}")
        fname = "{p}_consensus_{q}.{f}".format(p=slugify(project_name), q=slugify(question), f=format_.lower())
        fpath = file_path(fname, dir_)
        clean_files(fpath)
        if format_ == "csv":
            df.to_csv(fpath, sep=sep, index=True, header=True)
        else:  # json
            df.to_json(fpath, orient="index", indent=4)
        output_files.append(fpath)
        logger.debug(f"Consensus for {question} written into {fpath}.")
    return output_files
