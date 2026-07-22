# ---- Build stage ----
FROM public.ecr.aws/lambda/python:3.14@sha256:ffd4cb57ef54ca866520300d4489b624ee7d91c40f2d6e7bb415a7e8c2a3396e AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.31@sha256:ecd4de2f060c64bea0ff8ecb182ddf46ba3fcccdc8a60cfdbaf20d1a047d7437 /uv /uvx /bin/

COPY pyproject.toml uv.lock ${LAMBDA_TASK_ROOT}/

RUN cd ${LAMBDA_TASK_ROOT} && \
  uv export --format requirements-txt --no-hashes --no-dev > requirements.txt && \
  uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}" --no-cache --system

COPY . ${LAMBDA_TASK_ROOT}/

# ---- Runtime stage ----
FROM public.ecr.aws/lambda/python:3.14@sha256:ffd4cb57ef54ca866520300d4489b624ee7d91c40f2d6e7bb415a7e8c2a3396e

COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}

CMD ["lambdas.tokenizer_handler.lambda_handler"]
