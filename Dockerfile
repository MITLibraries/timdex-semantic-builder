# ---- Build stage ----
FROM public.ecr.aws/lambda/python:3.14@sha256:b6333b8065fbea995c6c816e06b81e269e30da3e2bd12a9365feb47826082982 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /uvx /bin/

COPY pyproject.toml uv.lock ${LAMBDA_TASK_ROOT}/

RUN cd ${LAMBDA_TASK_ROOT} && \
  uv export --format requirements-txt --no-hashes --no-dev > requirements.txt && \
  uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}" --no-cache --system

COPY . ${LAMBDA_TASK_ROOT}/

# ---- Runtime stage ----
FROM public.ecr.aws/lambda/python:3.14@sha256:b6333b8065fbea995c6c816e06b81e269e30da3e2bd12a9365feb47826082982

COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}

CMD ["lambdas.tokenizer_handler.lambda_handler"]
