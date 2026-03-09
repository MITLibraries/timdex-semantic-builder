import logging
import os

import sentry_sdk

# Load .env file. Generally only used in local dev as we exclude from git and docker
from dotenv import load_dotenv
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Config:
    REQUIRED_ENV_VARS = ("WORKSPACE",)
    OPTIONAL_ENV_VARS = ("LOG_LEVEL", "SENTRY_DSN", "WARNING_ONLY_LOGGERS")

    def check_required_env_vars(self) -> None:
        """Method to raise exception if required env vars not set."""
        missing_vars = [var for var in self.REQUIRED_ENV_VARS if not os.getenv(var)]
        if missing_vars:
            message = f"Missing required environment variables: {', '.join(missing_vars)}"
            raise OSError(message)

    @property
    def workspace(self) -> str | None:
        return os.getenv("WORKSPACE")

    @property
    def sentry_dsn(self) -> str | None:
        dsn = os.getenv("SENTRY_DSN")
        if dsn and dsn.strip().lower() != "none":
            return dsn
        return None

    @property
    def log_level(self) -> int:
        level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        return getattr(logging, level_str, logging.INFO)


def configure_logger(
    root_logger: logging.Logger,
    *,
    warning_only_loggers: str | None = None,
) -> str:
    """Configure application via passed application root logger."""
    root_logger.setLevel(Config().log_level)
    logging_format = "%(asctime)s %(levelname)s %(name)s.%(funcName)s(): %(message)s"

    warning_only_loggers = os.getenv("WARNING_ONLY_LOGGERS", warning_only_loggers)
    if warning_only_loggers:
        for name in warning_only_loggers.split(","):
            logging.getLogger(name).setLevel(logging.WARNING)

    # Clear any existing handlers to prevent duplication in AWS Lambda environment
    # where container may be reused between invocations
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(logging_format))
    root_logger.addHandler(handler)

    return (
        f"Logger '{root_logger.name}' configured with level="
        f"{logging.getLevelName(root_logger.getEffectiveLevel())}"
    )


def configure_sentry() -> None:
    CONFIG = Config()  # noqa: N806
    env = CONFIG.workspace
    if CONFIG.sentry_dsn:
        sentry_sdk.init(
            dsn=CONFIG.sentry_dsn,
            environment=env,
            integrations=[
                AwsLambdaIntegration(),
            ],
            traces_sample_rate=1.0,
        )
        logger.info(
            "Sentry DSN found, exceptions will be sent to Sentry with env=%s", env
        )
    else:
        logger.info("No Sentry DSN found, exceptions will not be sent to Sentry")
