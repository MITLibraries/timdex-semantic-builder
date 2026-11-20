# ---- Build stage ----
FROM public.ecr.aws/lambda/python:3.14@sha256:497df5d229e6d5c54279a6a48e7f597ff386bd02a9b3b37e788bb881108fc081 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.31@sha256:ecd4de2f060c64bea0ff8ecb182ddf46ba3fcccdc8a60cfdbaf20d1a047d7437 /uv /uvx /bin/

COPY pyproject.toml uv.lock ${LAMBDA_TASK_ROOT}/

RUN cd ${LAMBDA_TASK_ROOT} && \
  uv export --format requirements-txt --no-hashes --no-dev > requirements.txt && \
  uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}" --no-cache --system

COPY . ${LAMBDA_TASK_ROOT}/

# ---- Runtime stage ----
FROM public.ecr.aws/lambda/python:3.14@sha256:497df5d229e6d5c54279a6a48e7f597ff386bd02a9b3b37e788bb881108fc081

COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}

CMD ["lambdas.tokenizer_handler.lambda_handler"]
