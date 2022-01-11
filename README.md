# crowdnalysis-service
A service to compute and export the consensus for tasks in 
[Citizen Science Project Builder](https://lab.citizenscience.ch/) via 
[crowdnalysis](https://github.com/Crowd4SDG/crowdnalysis).

The service acts as an intermediary between the [C3S](https://github.com/CitizenScienceCenter/c3s-lab-client) frontend 
of Citizen Science Project Builder and the underlying 
[Pybossa API](https://docs.pybossa.com/api/intro/). 
The use case is as follows:
1. CS Project Builder user clicks the *Export Results* (in CSV or JSON format) button on the C3S frontend;
2. The request is forwarded to the crowdnalysis-service;
3. The service 
   - Calls Pybossa API to extract `task`, `task_run` and `result` data,
   - Computes the *consensus* on tasks for each *question* asked to the crowd by using crowdnalysis with the 
given consensus *model* (Dawid-Skene by default),
   - Creates a `CSV` or a `JSON` file for each consensus depending on user's request,
   - Sends the consensus and original result files back to the C3S in a `.zip` file;
4. The user downloads the `.zip` file without leaving the C3S frontend in any of the above steps.

If consensus does not apply to the project (*e.g.*, there is no classification task) or an error occurs during 
consensus computation, only the result files are returned. Log messages are sent to the `stderr`.

## Starting the service
The service is basically a [Flask](https://flask.palletsprojects.com/) application running on a 
[Gunicorn](https://gunicorn.org/) WSGI server and listening on the `5000` port. After git cloning the repo, 
start the service:

### As a standalone app
```bash
source bin/init.sh && bin/boot.sh 
```

### As a docker container
First, build the docker image:
```bash
docker build --tag crowdnalysis-service .
```

Then, run the container (in detached mode):
```bash
docker run -d -p 5000:5000 --env-file service.env crowdnalysis-service
```

> If you run the service on the same host with Pybossa, use the following command instead: 
> ```bash
> docker run -d -p 5000:5000 --env-file service.env --add-host host.docker.internal:host-gateway crowdnalysis-service
> ``` 

### Customization
- Edit the `service.env` file to configure the `PORT` that the service listens on and, if you start the service as a 
container, set the `-p` option in `docker run` accordingly. 
- To view `DEBUG`-level log messages, set the related environment variable to `1` in the same file.

> When the service is started by `docker-compose` within the Pybossa multi-container set-up, the environment variables 
> are read from the `etc/crowdnalyis-service.env` file instead.

## Troubleshoot
### Docker image
- While building the docker image, if you experience the `'internal compiler error: Killed (program cc1plus)'` error 
during the installation of CmdStan, increase the memory dedicated to your Docker engine, and retry building.  