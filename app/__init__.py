"""Package for the separation of crowdnalysis-service's inner functions"""
import logging
import os
from logging.config import dictConfig

from flask import Flask


LOG_LEVEL = logging.DEBUG if int(os.environ.get("CROWDNALYSIS_SERVICE_DEBUG", 0)) else logging.INFO

# Configure the logs for Flask app
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {"default": {
        "format": "[%(asctime)s] %(levelname)s: %(message)s",
    }},
    "handlers": {
        "wsgi": {
            "class": "logging.StreamHandler",
            "stream": "ext://flask.logging.wsgi_errors_stream",
            "formatter": "default"
        }
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["wsgi"],
            "level": logging.WARNING,
            "propagate": False
        },
        "crowdnalysis-service": {
            "level": LOG_LEVEL,
            "handlers": ["wsgi"],
            "propagate": False
        }
    }
})

logger = logging.getLogger("crowdnalysis-service")


def create_app():
    """Create a Flask application"""
    app = Flask(__name__)
    return app
