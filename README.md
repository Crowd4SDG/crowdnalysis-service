# crowdnalysis-service
A service to compute and export the consensus for tasks in CS Project Builder via 
[crowdnalysis](https://github.com/Crowd4SDG/crowdnalysis).

The service acts as an intermediary between the C3S frontend of 
[Citizen Science Project Builder](https://lab.citizenscience.ch/) and the underlying Pybossa API. 
The use case is as follows:
1. The CS Project Builder user clicks Export Results button on the C3S frontend;
2. The request is forwarded to the crowdnalysis-service;
3. The service 
   - Calls Pybossa API to extract `task`, `task_run` and `result` data,
   - Computes the **consensus** on tasks for each *question* that was asked to the crowd using  
the given consensus *model*,
   - Creates a `CSV` file for each consensus,
   - Sends the result and consensus files back to the C3S in a `zip` file;
4. The user downloads the `.zip` file without leaving the C3S frontend in any of the above steps.

When completed, the service is intended to run as a container in 
[pybossa-dev](https://github.com/Crowd4SDG/pybossa-dev).

## Start the service
The service is basically a [Flask](https://flask.palletsprojects.com/) application running on a 
[Gunicorn](https://gunicorn.org/) WSGI server. After git cloning the repo, start the service by running:

```bash
$ source bin/init.sh && source bin/boot.sh
```