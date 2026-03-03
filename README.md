# python-lambda-template

A template repository for creating Python lambda functions.

## Repo Setup (delete this section and above after initial function setup)

1. Rename "my_function" to the desired initial function name across the repo. (May be helpful to do a project-wide find-and-replace).
2. Update Python version if needed (note: AWS lambda cannot currently support versions higher than 3.9).
3. Install all dependencies with `make install`  to create initial Pipfile.lock with latest dependency versions.
4. Add initial function description to README and update initial required ENV variable documentation as needed.
5. Update license if needed (check app-specific dependencies for licensing terms).
6. Check Github repository settings:
   - Confirm repo branch protection settings are correct (see [dev docs](https://mitlibraries.github.io/guides/basics/github.html) for details)
   - Confirm that all of the following are enabled in the repo's code security and analysis settings:
      - Dependabot alerts
      - Dependabot security updates
      - Secret scanning
7. Create a Sentry project for the app if needed (we want this for most apps):
   - Send initial exceptions to Sentry project for dev, stage, and prod environments to create them.
   - Create an alert for the prod environment only, with notifications sent to the appropriate team(s).
   - If *not* using Sentry, delete Sentry configuration from my_function.py and test_my_function_.py, and remove sentry_sdk from project dependencies.

# my_function

Description of the function/functions.

## Development

- To preview a list of available Makefile commands: `make help`
- To create a Python virtual environment and install with dev dependencies: `make install`
- To update dependencies: `make update`
- To run unit tests: `make test`
- To lint the repo: `make lint`

## Testing Locally with AWS SAM

### SAM Installation

Ensure that AWS SAM CLI is installed: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html.

All following actions and commands should be performed from the root of the project (i.e. same directory as the `Dockerfile`).

### Building and Configuration

1- Create a JSON file for SAM that has environment variables for the container 

- copy `tests/sam/env.json.template` to `tests/sam/env.json` (which is git ignored)
- fill in missing sensitive env vars

**NOTE:** AWS credentials are automatically passed from the terminal context that runs `make sam-run`; they do not need to be explicitly set as env vars.

2- Build Docker image:

```shell
make sam-build
```

### Invoking Lambda via HTTP requests

The following outlines how to run the Lambda SAM docker image as an HTTP endpoint, accepting requests and returning respnoses similar to a lambda behind an ALB, Function URL, or API Gateway.

1- Ensure any required AWS credentials set in terminal, and any other env vars in `tests/sam/env.json` up-to-date.

2- Run HTTP server:

```shell
make sam-http-run
```

This starts a server at `http://localhost:3000`.  Requests must include a path, e.g. `/myapp`, but are arbitrary insofar as the lambda does not utilize them in the request payload. 

3- In another terminal, perform an HTTP request via another `Makefile` command:

```shell
make sam-http-ping
```

Response should have an HTTP status of `200` and respond with:

```json
You have successfully called this lambda!
```

### Invoking Lambda directly

While Lambdas can be invoked via HTTP methods (ALB, Function URL, etc.), they are also often invoked directly with an `event` payload.  To do so with SAM, you do **not** need to first start an HTTP server with `make sam-run`, you can invoke the function image directly:

```shell
echo '{"action": "ping"}' | sam local invoke -e -
```

Response:

```text
You have successfully called this lambda!
```

As you can see from this response, the returning the same content even though it was invoked directly.

### Troubleshoot

#### Encounter error `botocore.exceptions.TokenRetrievalError`

When running a Lambda via SAM, it attempts to parse and setup AWS credentials just like a real Lambda would establish them.  Depending on how you setup AWS credentials on your host machine, if they are stale or invalid, you may encounter this error when making your first requests of the Lambda.

**Solution:** Stop the SAM container, refresh AWS credentials, and restart it.

## Running locally without SAM

### Build the container

`docker build -t my_function:latest .`

### Run the container

`docker run -e WORKSPACE=dev -p 9000:8080 my_function:latest`

### Call the container via HTTP from another terminal window

`curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{ "query": "hello world"}'`

If you have `jq` installed, you can pipe the output to get better formatted output.

`curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{ "query": "hello world"}' | jq`

## Environment Variables

### Required

```shell
SENTRY_DSN=### If set to a valid Sentry DSN, enables Sentry exception monitoring. This is not needed for local development.
WORKSPACE=### Set to `dev` for local development, this will be set to `stage` and `prod` in those environments by Terraform.
```

### Optional

```shell
<OPTIONAL_ENV>=### Description for optional environment variable
```
