# syntax=docker/dockerfile:1
FROM python:3.9-buster

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
