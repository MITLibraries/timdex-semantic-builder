import json
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aws_lambda_typing.context import Context

from lambdas.config import Config, configure_logger, configure_sentry
from lambdas.query_tokenizer import QueryTokenizer

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
def lambda_handler(event: dict, lambda_context: Context) -> dict:
    """Main Lambda handler for tokenizing queries for OpenSearch.

    Returns a JSON-serializable dict; the AWS Lambda runtime handles serialization.
    """
    logger.debug("Received event: %s", event)
    logger.debug("Lambda context: %s", lambda_context)

    # Initialize once (reuse for multiple queries)
    query_tokenizer = QueryTokenizer()

    # Generate query tokens
    query = event.get("query", "")

    if not query.strip():
        logger.warning("Received empty query in event: %s", event)
        return {"error": "Query is required in the event payload."}

    start = time.time()
    query_tokens = query_tokenizer.tokenize_query(query)
    end = time.time()
    logger.debug("Tokenization and IDF weighting took: %.4f seconds", end - start)

    logger.debug("Query tokens for OpenSearch:")
    logger.debug(json.dumps(query_tokens, indent=2))

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
