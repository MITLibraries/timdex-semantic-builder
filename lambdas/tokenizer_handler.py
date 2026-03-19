import logging
import time
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aws_lambda_typing.context import Context

from lambdas.config import Config, configure_logger, configure_sentry
from lambdas.query_tokenizer import QueryTokenizer

# ---------------------------------------
# One-time, Lambda cold start setup
# ---------------------------------------
CONFIG = Config()
CONFIG.check_required_env_vars()

root_logger = logging.getLogger()
log_config_message = configure_logger(root_logger)
logger = logging.getLogger(__name__)
logger.info(log_config_message)

configure_sentry()


@lru_cache(maxsize=1)
def _get_tokenizer() -> QueryTokenizer:
    """Return the module-level QueryTokenizer, created once and cached."""
    logger.info("Initializing QueryTokenizer (cold start)")
    return QueryTokenizer()


# ---------------------------------------
# Lambda handler entrypoint
# ---------------------------------------
def lambda_handler(event: dict, lambda_context: Context) -> dict:
    """Main Lambda handler for tokenizing queries for OpenSearch.

    Returns a JSON-serializable dict; the AWS Lambda runtime handles serialization.
    """
    logger.debug("Received event: %s", event)
    logger.debug("Lambda context: %s", lambda_context)

    query_tokenizer = _get_tokenizer()

    # Handle ping or health check events
    # We add this after query_tokenizer initialization to ensure the tokenizer is
    # initialized during cold start, even for pings
    if event.get("ping"):
        logger.info("Received ping event")
        return {"status": "ok"}

    # Generate query tokens
    query = event.get("query", "")

    if not query.strip():
        logger.warning("Received empty query in event: %s", event)
        return {"error": "Query is required in the event payload."}

    start = time.perf_counter()
    query_tokens = query_tokenizer.tokenize_query(query)
    end = time.perf_counter()
    logger.debug("Tokenization and IDF weighting took: %.4f seconds", end - start)

    # Build OpenSearch query
    return {
        "query": {
            "bool": {
                "should": [
                    {
                        "rank_feature": {
                            "field": f"embedding_full_record.{token}",
                            "boost": weight,
                        }
                    }
                    for token, weight in query_tokens.items()
                ]
            }
        }
    }
