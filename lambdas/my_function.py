import json
import logging

from lambdas.config import Config, configure_logger, configure_sentry

# ---------------------------------------
# One-time, Lambda cold start setup
# ---------------------------------------
CONFIG = Config()

root_logger = logging.getLogger()
log_config_message = configure_logger(root_logger)
logger = logging.getLogger(__name__)
logger.info(log_config_message)

configure_sentry()


# ---------------------------------------
# Lambda handler entrypoint
# ---------------------------------------
def lambda_handler(event: dict, lambda_context: dict) -> str:
    logger.debug(json.dumps(event))
    logger.info("LaLambda context: %s", lambda_context)
    return "You have successfully called this lambda!"
