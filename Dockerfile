# syntax=docker/dockerfile:1
FROM python:3.9-slim-buster

ARG CROWDNALYSIS_SERVICE_HOST=localhost
ARG CROWDNALYSIS_SERVICE_PORT=5000
ARG CROWDNALYSIS_SERVICE_DEBUG=0

RUN adduser --disabled-password --gecos '' crowdnalysis
USER crowdnalysis

# RUN MKDIR /app
WORKDIR /app
COPY requirements.txt requirements.txt
COPY ./bin/init.sh ./bin/boot.sh bin/

# Create virtualenv and install dependencies on the image
RUN bin/init.sh

COPY service.py .

# Run-time configuration
EXPOSE $CROWDNALYSIS_SERVICE_PORT
ENTRYPOINT ["bin/boot.sh", "in_container"]
