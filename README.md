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

## Notes on automated deployment in AWS

Due to the need for provisioned concurrency to keep this Lambda warm, it diverges a bit from our standard dev/stage/prod deployment workflows as noted below.

Each of the three GitHub Actions workflows ([dev-build](.github/workflows/dev-build.yml), [stage-build](.github/workflows/stage-build.yml), [prod-deploy](.github/workflows/prod-deploy.yml)) has an additional job to handle the extra deployment steps to ensure that the provisioned concurrency works correctly. This job handles three steps:

1. Publish the latest version of the Lambda function.
1. Update the "live" alias to the function so that it points to the most recent published version of the function.
1. Clean up leftover published versions of the function, leaving the latest and next-most latest published versions in place.

These extra steps are necessary because the infrastructure configures a Lambda alias and associates the provisioned concurrency to that alias.

### Handling AWS Latency

There are some inherent delays/latency in AWS around Lambda function deployment, version publishing, and alias assignment that require some additional work in the GHA workflows.

#### Lambda Publishing Latency

After deploying a new Lambda with the shared `ecr-multi-arch-deploy-<env>` workflow, there is a delay before that new Lambda is even available for publishing. Thankfully, AWS has a `wait` command as part of the `aws lambda` CLI command ([AWS Docuentation on `wait`](https://docs.aws.amazon.com/cli/latest/reference/lambda/wait/)). The **Publish New Version** step in the workflows uses `aws lambda wait` to ensure that the deployed Lambda is ready for "publishing" before running the `aws lambda publish-version` command.

Then there is another delay while AWS prepares the published version, so we use the `aws lambda wait` again to ensure that the published version is available before allowing the **Publish New Version** step to complete.

#### Alias Assignment Latency

There is also some inherent latency around the process of assigning an alias to a published Lambda (see the **Update Lambda Alias** step in the workflows). Unfortunately, the `aws lambda wait` cannot help here! After assigning the `"live"` alias to the latest published version of the Lambda function, there is a window of time when the alias is linked to more than one published version and a routing config is temporarily in place. This can be seen with the `aws lambda get-alias` command:

```bash
% aws lambda get-alias --region <region> --function-name <function_name> --name <alias_name>
14
% aws lambda get-alias --region <region> --function-name <function_name> --name <alias_name>
{
    "AliasArn": "arn:aws:lambda:<region>:xxxxxxxxxx:function:<function_name>:<alias_name>",
    "Name": "<alias_name>",
    "FunctionVersion": "14",
    "Description": "Alias to <function_name> Lambda function; necessary for provisioned capacity",
    "RoutingConfig": {
        "AdditionalVersionWeights": {
            "13": 1.0
        }
    },
    "RevisionId": "<UUID>"
}
```

Once the alias has stabilized, the output from the `aws lambda get-alias` command no longer has the `RoutingConfig` key:

```json
{
    "AliasArn": "arn:aws:lambda:<region>:xxxxxxxxxx:function:<function_name>:<alias_name>",
    "Name": "<alias_name>",
    "FunctionVersion": "14",
    "Description": "Alias to <function_name> Lambda function; necessary for provisioned capacity",
    "RevisionId": "<UUID>"
}
```

Since we cannot use `aws lambda wait`, we build a `while` loop poller that checks this output and smoothly exits once the `RoutingConfig` key disappears from the output. If the while loop finishes without the `RoutingConfig` key disappearing during the configured timeout (currently 5 minutes), the **Update Lambda Alias** step exits with an error code.

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
