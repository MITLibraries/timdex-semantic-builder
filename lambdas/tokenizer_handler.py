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


def _build_opensearch_query(
    query_tokens: dict[str, float],
    *,
    must_boost_threshold: float = MUST_BOOST_THRESHOLD,
    drop_boost_threshold: float = DROP_BOOST_THRESHOLD,
    short_query_max_tokens: int = SHORT_QUERY_MAX_TOKENS,
) -> dict:
    """Build an OpenSearch bool query from a token→weight mapping.

    High-weight tokens (>= must_boost_threshold * max) go into `must`.
    Low-weight tokens (< drop_boost_threshold * max) are dropped when the
    query has more than short_query_max_tokens tokens (kept otherwise).
    Remaining tokens go into `should`. Keys are omitted from the bool dict
    when their clause list would be empty.

    Threshold parameters default to the module-level constants and can be
    overridden per-call during tuning via the Lambda event payload.
    """
    if not query_tokens:
        # Avoid emitting an empty bool query, which would behave like a match_all.
        return {"query": {"bool": {"must_not": [{"match_all": {}}]}}}

    max_weight = max(query_tokens.values())

    tokens = dict(query_tokens)

    # Drop extremely low-weight tokens only for longer queries
    if len(tokens) > short_query_max_tokens:
        drop_cutoff = max_weight * drop_boost_threshold
        dropped = {t: w for t, w in tokens.items() if w < drop_cutoff}
        if dropped:
            logger.debug("Dropped low-weight tokens: %s", dropped)
        tokens = {t: w for t, w in tokens.items() if w >= drop_cutoff}

    must_cutoff = max_weight * must_boost_threshold
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

    # When absent or invalid, fall back to module-level defaults.
    must_raw = event.get("must_boost_threshold", MUST_BOOST_THRESHOLD)
    drop_raw = event.get("drop_boost_threshold", DROP_BOOST_THRESHOLD)
    short_raw = event.get("short_query_max_tokens", SHORT_QUERY_MAX_TOKENS)
    try:
        must_boost_threshold = float(must_raw)
    except TypeError, ValueError:
        logger.warning("Invalid must_boost_threshold override: %r", must_raw)
        must_boost_threshold = MUST_BOOST_THRESHOLD
    try:
        drop_boost_threshold = float(drop_raw)
    except TypeError, ValueError:
        logger.warning("Invalid drop_boost_threshold override: %r", drop_raw)
        drop_boost_threshold = DROP_BOOST_THRESHOLD
    try:
        short_query_max_tokens = int(short_raw)
    except TypeError, ValueError:
        logger.warning("Invalid short_query_max_tokens override: %r", short_raw)
        short_query_max_tokens = SHORT_QUERY_MAX_TOKENS
    must_boost_threshold = max(0.0, min(1.0, must_boost_threshold))
    drop_boost_threshold = max(0.0, min(1.0, drop_boost_threshold))
    short_query_max_tokens = max(0, short_query_max_tokens)

    logger.debug(
        "Query thresholds — must: %.2f, drop: %.2f, short_query_max: %d",
        must_boost_threshold,
        drop_boost_threshold,
        short_query_max_tokens,
    )

    # Build OpenSearch query
    return _build_opensearch_query(
        query_tokens,
        must_boost_threshold=must_boost_threshold,
        drop_boost_threshold=drop_boost_threshold,
        short_query_max_tokens=short_query_max_tokens,
    )
