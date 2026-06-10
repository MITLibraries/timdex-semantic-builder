import logging
import time
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aws_lambda_typing.context import Context

from lambdas.config import Config, configure_logger, configure_sentry
from lambdas.query_tokenizer import QueryTokenizer

# ---------------------------------------
# Query construction thresholds
# ---------------------------------------

# Tokens whose weight is >= this fraction of the max weight are placed in the `must`
# block.
MUST_BOOST_THRESHOLD = 0.70

# Tokens whose weight is < this fraction of the max weight are dropped entirely,
# but only when there are more than SHORT_QUERY_MAX_TOKENS tokens (to avoid discarding
# meaningful signal from short queries).
DROP_BOOST_THRESHOLD = 0.10

# Queries with this many tokens or fewer are considered "short" — no tokens are dropped.
# This does NOT mean all words are required, as some may still fall below the
# MUST_BOOST_THRESHOLD and go into `should`.
SHORT_QUERY_MAX_TOKENS = 5

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


def _build_opensearch_query(query_tokens: dict[str, float]) -> dict:
    """Build an OpenSearch bool query from a token→weight mapping.

    High-weight tokens (>= MUST_BOOST_THRESHOLD * max) go into `must`.
    Low-weight tokens (< DROP_BOOST_THRESHOLD * max) are dropped when the
    query has more than SHORT_QUERY_MAX_TOKENS tokens (kept otherwise).
    Remaining tokens go into `should`. Keys are omitted from the bool dict
    when their clause list would be empty.
    """
    if not query_tokens:
        return {"query": {"bool": {}}}

    max_weight = max(query_tokens.values())

    tokens = dict(query_tokens)

    # Drop extremely low-weight tokens only for longer queries
    if len(tokens) > SHORT_QUERY_MAX_TOKENS:
        drop_cutoff = max_weight * DROP_BOOST_THRESHOLD
        dropped = {t: w for t, w in tokens.items() if w < drop_cutoff}
        if dropped:
            logger.debug("Dropped low-weight tokens: %s", dropped)
        tokens = {t: w for t, w in tokens.items() if w >= drop_cutoff}

    must_cutoff = max_weight * MUST_BOOST_THRESHOLD
    must_clauses = []
    should_clauses = []

    for token, weight in tokens.items():
        clause = {
            "rank_feature": {"field": f"embedding_full_record.{token}", "boost": weight}
        }
        if weight >= must_cutoff:
            must_clauses.append(clause)
        else:
            should_clauses.append(clause)

    bool_query: dict = {}
    if must_clauses:
        bool_query["must"] = must_clauses
    if should_clauses:
        bool_query["should"] = should_clauses

    return {"query": {"bool": bool_query}}


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
    if "ping" in event:
        logger.debug("Received ping event")
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
    return _build_opensearch_query(query_tokens)
