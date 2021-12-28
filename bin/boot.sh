#!/usr/bin/env bash
echo "Booting crowdnalysis-service..."

export FLASK_APP=service.py
export FLASK_DEBUG=${CROWDNALYSIS_SERVICE_DEBUG:-0}

source .venv/bin/activate

if [[ "$1" == "in_container" ]]; then
    if [[ -z "$PYBOSSA_API_HOST" || "$PYBOSSA_API_HOST" == "localhost" ]]; then
      export PYBOSSA_API_HOST="host.docker.internal"  # resolves to the internal IP address used by the host
    fi
    echo "Starting the service in a Docker container."
fi

echo "CROWDNALYSIS_SERVICE_PORT: ${CROWDNALYSIS_SERVICE_PORT:-5000}"
echo "PYBOSSA_API_HOST: ${PYBOSSA_API_HOST}"

# Start Gunicorn WSGI server
exec gunicorn -b 0.0.0.0:${CROWDNALYSIS_SERVICE_PORT:-5000} --access-logfile - --error-logfile - service:app
