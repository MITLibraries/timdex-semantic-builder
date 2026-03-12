# timdex-semantic-builder

Accepts query string (keyword) and returns OpenSearch-ready token weights.

## Development

- To preview a list of available Makefile commands: `make help`
- To create a Python virtual environment and install with dev dependencies: `make install`
- To update dependencies: `make update`
- To run unit tests: `make test`
- To lint the repo: `make lint`

## opensearch-project directory

This directory stores 3 files extracted from the `opensearch-neural-sparse-encoding-doc-v3-gte` model.

We store them locally to reduce unnecessary downloads from huggingface, and because we don't need the full model, just these files.

This repository should refresh these files whenever our pipeline repository updates the model version.

## Testing Locally with AWS SAM

### SAM Installation

Ensure that AWS SAM CLI is installed: <https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html>.

All following actions and commands should be performed from the root of the project (i.e. same directory as the `Dockerfile`).

### Building and Configuration

1- Create a JSON file for SAM that has environment variables for the container

- copy `tests/sam/env.json.template` to `tests/sam/env.json` (which is git ignored)
- fill in missing sensitive env vars

**NOTE:** AWS credentials are automatically passed from the terminal context that runs `make sam-run`; they do not need to be explicitly set as env vars.

2- Build Docker image:

> [!TIP]
> This step can take a few minutes and may appear to hang.

```shell
make sam-build
```

> [!IMPORTANT]
> You need to rebuild when you change code.

### Invoking Lambda directly

While Lambdas can be invoked via HTTP methods (ALB, Function URL, etc.), they are also often invoked directly with an `event` payload. You can invoke the function image directly:

```shell
echo '{"query": "hello world"}' | sam local invoke -e -
```

Response:

```json
{
  "query": {
    "bool": {
      "should": [
        {
          "rank_feature": {
            "field": "embedding_full_record.[CLS]",
            "boost": 1.0
          }
        },
        {
          "rank_feature": {
            "field": "embedding_full_record.[SEP]",
            "boost": 1.0
          }
        },
        {
          "rank_feature": {
            "field": "embedding_full_record.world",
            "boost": 3.4208686351776123
          }
        },
        {
          "rank_feature": {
            "field": "embedding_full_record.hello",
            "boost": 6.937756538391113
          }
        }
      ]
    }
  }
}
```

### Troubleshoot

#### Encounter error `botocore.exceptions.TokenRetrievalError`

When running a Lambda via SAM, it attempts to parse and setup AWS credentials just like a real Lambda would establish them.  Depending on how you setup AWS credentials on your host machine, if they are stale or invalid, you may encounter this error when making your first requests of the Lambda.

**Solution:** Stop the SAM container, refresh AWS credentials, and restart it.

## Running locally without SAM

### Build the container

`docker build -t tokenizer:latest .`

### Run the container

`docker run -e WORKSPACE=dev -p 9000:8080 tokenizer:latest`

### Call the container via HTTP from another terminal window

`curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{ "query": "hello world"}'`

If you have `jq` installed, you can pipe the output to get better formatted output.

`curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{ "query": "hello world"}' | jq`

### Open a python console with application context

- `make console`
- `from lambdas import tokenizer_handler`
- `tokenizer_handler.lambda_handler({"query": "hello world"}, {})`

Response:

```json
{
  "query":{
    "bool":{
      "should":[
        {
          "rank_feature":{
            "field":"embedding_full_record.[CLS]",
            "boost":1.0
          }
        },
        {
          "rank_feature":{
            "field":"embedding_full_record.[SEP]",
            "boost":1.0
          }
        },
        {
          "rank_feature":{
            "field":"embedding_full_record.world",
            "boost":3.4208686351776123
          }
        },
        {
          "rank_feature":{
            "field":"embedding_full_record.hello",
            "boost":6.937756538391113
          }
        }
      ]
    }
  }
}
```

## Environment Variables

In local development, you can add a `.env` file to manage these. The file is excluded from git and docker builds via
ignore files.

### Required

```shell
WORKSPACE=### Set to `dev` for local development, this will be set to `stage` and `prod` in those environments by Terraform.
```

### Optional

```shell
SENTRY_DSN=### If set to a valid Sentry DSN, enables Sentry exception monitoring. This is not needed for local development.
```
