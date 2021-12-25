# crowdnalysis-service
A service to compute and export the consensus for tasks in CS Project Builder via 
[crowdnalysis](https://github.com/Crowd4SDG/crowdnalysis).

The service acts as an intermediary between the C3S frontend of 
[Citizen Science Project Builder](https://lab.citizenscience.ch/) and the underlying 
[Pybossa API](https://docs.pybossa.com/api/intro/). 
The use case is as follows:
1. CS Project Builder user clicks the *Export Results* (in CSV or JSON format) button on the C3S frontend;
2. The request is forwarded to the crowdnalysis-service;
3. The service 
   - Calls Pybossa API to extract `task`, `task_run` and `result` data,
   - Computes the **consensus** on tasks for each *question* that was asked to the crowd using the 
given consensus *model*,
   - Creates a `CSV` or a `JSON` file for each consensus depending on user's request,
   - Sends the consensus and original result files back to the C3S in a `.zip` file;
4. The user downloads the `.zip` file without leaving the C3S frontend in any of the above steps.

## Start the service
The service is basically a [Flask](https://flask.palletsprojects.com/) application running on a 
[Gunicorn](https://gunicorn.org/) WSGI server. After git cloning the repo, start the service:

### As a standalone app
```bash
$ bin/init.sh && bin/boot.sh
```

### As a docker container
First, build the docker image:
```bash
$ docker build --tag crowdnalysis-service .
```
Then, run the container (in detached mode):
```bash
$ docker run -d -p 5000:5000 --network="bridge" crowdnalysis-service
```