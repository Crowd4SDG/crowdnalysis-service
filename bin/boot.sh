export FLASK_APP=service.py
export FLASK_DEBUG=${CROWDNALYSIS_SERVICE_DEBUG:-0}

source .venv/bin/activate

exec gunicorn -b ${CROWDNALYSIS_SERVICE_HOST:-localhost}:${CROWDNALYSIS_SERVICE_PORT:-5000} --access-logfile - --error-logfile - service:app