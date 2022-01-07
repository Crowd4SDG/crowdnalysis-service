#!/usr/bin/env bash
# Starts the service in standalone or docker container modes.

echo "Booting crowdnalysis-service..."

source .venv/bin/activate

if [[ "$1" == "in_container" ]]; then
  if [[ -z "$PYBOSSA_API_HOST" || "$PYBOSSA_API_HOST" == "localhost" ]]; then
    export PYBOSSA_API_HOST="host.docker.internal"  # resolves to the internal IP address used by the host
  fi
  echo "Starting the service in a Docker container."
else  # service as standalone app
  source service.env && export $(cut -d= -f1 service.env)
fi

export FLASK_APP=service.py

echo "CROWDNALYSIS_SERVICE_PORT: ${CROWDNALYSIS_SERVICE_PORT}"
echo "CROWDNALYSIS_SERVICE_DEBUG: ${CROWDNALYSIS_SERVICE_DEBUG}"
echo "PYBOSSA_API_HOST: ${PYBOSSA_API_HOST}"

# Start Gunicorn WSGI server with 4 worker processes for handling requests
exec gunicorn -w 4 -b 0.0.0.0:${CROWDNALYSIS_SERVICE_PORT} --access-logfile - --error-logfile - service:app
