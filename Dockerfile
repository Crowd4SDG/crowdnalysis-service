# syntax=docker/dockerfile:1
FROM python:3.9-buster

# Set default values for env vars that can be overwriten by the docker run --env-file option
ENV CROWDNALYSIS_SERVICE_PORT=5000
ENV CROWDNALYSIS_SERVICE_DEBUG=0
ENV PYBOSSA_API_HOST=localhost

# RUN adduser --disabled-password --gecos '' crowdnalysis
# USER crowdnalysis  # This unprivileged user causes permission errors while compiling Stan files

WORKDIR /app
COPY requirements.txt requirements.txt
COPY ./bin/init.sh ./bin/boot.sh bin/

# Create virtualenv and install dependencies on the image
RUN bin/init.sh

COPY service.py .

# Run-time configuration
EXPOSE $CROWDNALYSIS_SERVICE_PORT
ENTRYPOINT ["bin/boot.sh", "in_container"]
