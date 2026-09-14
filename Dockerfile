# ---- Build stage ----
FROM public.ecr.aws/lambda/python:3.14@sha256:ba6b4ce9b75532265d9c55ecf3f637f736eac4f23f060c767e6488dc1e47b3a9 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.31@sha256:ecd4de2f060c64bea0ff8ecb182ddf46ba3fcccdc8a60cfdbaf20d1a047d7437 /uv /uvx /bin/

COPY pyproject.toml uv.lock ${LAMBDA_TASK_ROOT}/

RUN cd ${LAMBDA_TASK_ROOT} && \
  uv export --format requirements-txt --no-hashes --no-dev > requirements.txt && \
  uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}" --no-cache --system

COPY . ${LAMBDA_TASK_ROOT}/

# ---- Runtime stage ----
FROM public.ecr.aws/lambda/python:3.14@sha256:ba6b4ce9b75532265d9c55ecf3f637f736eac4f23f060c767e6488dc1e47b3a9

COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}

CMD ["lambdas.tokenizer_handler.lambda_handler"]
