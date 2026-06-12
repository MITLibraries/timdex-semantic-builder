from unittest.mock import MagicMock, patch

import pytest

from lambdas import tokenizer_handler
from lambdas.tokenizer_handler import (
    DROP_BOOST_THRESHOLD,
    MUST_BOOST_THRESHOLD,
    SHORT_QUERY_MAX_TOKENS,
    _build_opensearch_query,
)


@pytest.fixture
def mock_query_tokenizer():
    mock_instance = MagicMock()
    with patch.object(tokenizer_handler, "_get_tokenizer", return_value=mock_instance):
        yield mock_instance


def test_returns_opensearch_query_structure(mock_query_tokenizer):
    mock_query_tokenizer.tokenize_query.return_value = {"hello": 1.5, "world": 2.0}
    result = tokenizer_handler.lambda_handler({"query": "hello world"}, {})
    assert "query" in result
    assert "bool" in result["query"]
    bool_query = result["query"]["bool"]
    assert "must" in bool_query or "should" in bool_query


def test_opensearch_query_contains_rank_features(mock_query_tokenizer):
    # With a single token it will go to must (it is 100% of max)
    mock_query_tokenizer.tokenize_query.return_value = {"hello": 1.5}
    result = tokenizer_handler.lambda_handler({"query": "hello"}, {})
    must_clauses = result["query"]["bool"]["must"]
    assert len(must_clauses) == 1
    assert must_clauses[0]["rank_feature"]["field"] == "embedding_full_record.hello"
    assert must_clauses[0]["rank_feature"]["boost"] == pytest.approx(1.5)


def test_returns_no_query_provided_for_empty_query(mock_query_tokenizer):
    result = tokenizer_handler.lambda_handler({"query": ""}, {})
    assert result == {"error": "Query is required in the event payload."}
    mock_query_tokenizer.tokenize_query.assert_not_called()


def test_returns_no_query_provided_when_query_key_missing(mock_query_tokenizer):
    result = tokenizer_handler.lambda_handler({}, {})
    assert result == {"error": "Query is required in the event payload."}
    mock_query_tokenizer.tokenize_query.assert_not_called()


def test_each_token_weight_pair_becomes_rank_feature(mock_query_tokenizer):
    mock_query_tokenizer.tokenize_query.return_value = {"foo": 1.0, "bar": 3.5}
    result = tokenizer_handler.lambda_handler({"query": "foo bar"}, {})
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert fields == {"embedding_full_record.foo", "embedding_full_record.bar"}


def test_tokenize_query_called_with_correct_query(mock_query_tokenizer):
    mock_query_tokenizer.tokenize_query.return_value = {"fakedata": 1.5}
    tokenizer_handler.lambda_handler({"query": "hello world"}, {})
    mock_query_tokenizer.tokenize_query.assert_called_once_with("hello world")


def test_returns_error_for_whitespace_only_query(mock_query_tokenizer):
    result = tokenizer_handler.lambda_handler({"query": "   "}, {})
    assert result == {"error": "Query is required in the event payload."}
    mock_query_tokenizer.tokenize_query.assert_not_called()


def test_ping_event_returns_ok_status(mock_query_tokenizer):
    result = tokenizer_handler.lambda_handler({"ping": True}, {})
    assert result == {"status": "ok"}


def test_ping_event_does_not_call_tokenize_query(mock_query_tokenizer):
    tokenizer_handler.lambda_handler({"ping": True}, {})
    mock_query_tokenizer.tokenize_query.assert_not_called()


def test_non_ping_event_is_not_short_circuited(mock_query_tokenizer):
    mock_query_tokenizer.tokenize_query.return_value = {"hello": 1.5}
    result = tokenizer_handler.lambda_handler({"query": "hello"}, {})
    assert "query" in result
    mock_query_tokenizer.tokenize_query.assert_called_once()


# ---------------------------------------------------------------------------
# _build_opensearch_query unit tests
# ---------------------------------------------------------------------------


def test_high_weight_token_goes_to_must():
    # max=10.0; 10.0 >= 7.0 (70% of 10) → must
    tokens = {"high": 10.0, "low": 1.0}
    result = _build_opensearch_query(tokens)
    must_fields = {c["rank_feature"]["field"] for c in result["query"]["bool"]["must"]}
    assert "embedding_full_record.high" in must_fields


def test_low_weight_token_goes_to_should():
    # max=10.0; 1.0 < 7.0 (70% of 10) → should
    tokens = {"high": 10.0, "low": 1.0}
    result = _build_opensearch_query(tokens)
    should_fields = {
        c["rank_feature"]["field"] for c in result["query"]["bool"]["should"]
    }
    assert "embedding_full_record.low" in should_fields


def test_all_high_weight_tokens_produce_only_must_block():
    # All tokens within 70%+ of max → only must, no should key
    tokens = {"a": 10.0, "b": 9.0, "c": 8.0}
    result = _build_opensearch_query(tokens)
    bool_query = result["query"]["bool"]
    assert "must" in bool_query
    assert "should" not in bool_query


def test_must_threshold_is_applied_relative_to_max():
    # dominant token sets max; just_above and just_below straddle the 70% cutoff
    max_w = 10.0
    must_cutoff = max_w * MUST_BOOST_THRESHOLD
    tokens = {
        "dominant": max_w,
        "just_above": must_cutoff + 0.01,
        "just_below": must_cutoff - 0.01,
    }
    result = _build_opensearch_query(tokens)
    bool_query = result["query"]["bool"]
    must_fields = {c["rank_feature"]["field"] for c in bool_query.get("must", [])}
    should_fields = {c["rank_feature"]["field"] for c in bool_query.get("should", [])}
    assert "embedding_full_record.just_above" in must_fields
    assert "embedding_full_record.just_below" in should_fields


def test_low_weight_token_dropped_when_many_features():
    # Build SHORT_QUERY_MAX_TOKENS+1 tokens; one is near-zero → should be dropped
    tokens = {
        f"t{i}": float(10 - i) for i in range(SHORT_QUERY_MAX_TOKENS)
    }  # normal weights
    tokens["near_zero"] = 0.001  # well below DROP_BOOST_THRESHOLD * max
    assert len(tokens) == SHORT_QUERY_MAX_TOKENS + 1

    result = _build_opensearch_query(tokens)
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    all_fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert "embedding_full_record.near_zero" not in all_fields


def test_low_weight_token_kept_when_few_features():
    # SHORT_QUERY_MAX_TOKENS or fewer tokens → no dropping regardless of weight
    tokens = {"dominant": 10.0, "tiny": 0.001}
    assert len(tokens) <= SHORT_QUERY_MAX_TOKENS

    result = _build_opensearch_query(tokens)
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    all_fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert "embedding_full_record.tiny" in all_fields


def test_drop_threshold_is_applied_relative_to_max():
    max_w = 10.0
    drop_cutoff = max_w * DROP_BOOST_THRESHOLD
    # Filler tokens at max_w to anchor the max; keep/drop straddle the drop cutoff
    tokens = {f"filler{i}": max_w for i in range(SHORT_QUERY_MAX_TOKENS)}
    tokens["keep"] = drop_cutoff + 0.01
    tokens["drop"] = drop_cutoff - 0.01
    assert len(tokens) > SHORT_QUERY_MAX_TOKENS

    result = _build_opensearch_query(tokens)
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    all_fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert "embedding_full_record.keep" in all_fields
    assert "embedding_full_record.drop" not in all_fields


def test_no_tokens_dropped_when_all_weights_are_above_drop_threshold():
    # Many tokens, but all weights well above the drop cutoff → all are retained
    tokens = {f"t{i}": float(10 - i * 0.1) for i in range(SHORT_QUERY_MAX_TOKENS + 1)}
    assert len(tokens) > SHORT_QUERY_MAX_TOKENS

    result = _build_opensearch_query(tokens)
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    assert len(all_clauses) == len(tokens)


def test_empty_tokens_returns_match_none_bool_query():
    result = _build_opensearch_query({})
    assert result == {"query": {"bool": {"must_not": [{"match_all": {}}]}}}


def test_event_threshold_overrides_are_used(mock_query_tokenizer):
    # With high=10.0 and low=9.9, demonstrate that the same input produces different
    # outputs based on must_boost_threshold:
    # - Default (0.70): 9.9 >= 7.0 → low goes to must
    # - Override (1.0): 9.9 < 10.0 → low goes to should
    mock_query_tokenizer.tokenize_query.return_value = {"high": 10.0, "low": 9.9}

    # First: with default threshold, low should be in must
    result_default = tokenizer_handler.lambda_handler(
        {"query": "high low"},
        {},
    )
    bool_query_default = result_default["query"]["bool"]
    expected_must_default = {
        c["rank_feature"]["field"] for c in bool_query_default.get("must", [])
    }
    assert "embedding_full_record.high" in expected_must_default
    assert "embedding_full_record.low" in expected_must_default
    assert "should" not in bool_query_default

    # Second: with override threshold=1.0, low should move to should
    result_override = tokenizer_handler.lambda_handler(
        {"query": "high low", "must_boost_threshold": 1.0},
        {},
    )
    bool_query_override = result_override["query"]["bool"]
    expected_must_override = {
        c["rank_feature"]["field"] for c in bool_query_override.get("must", [])
    }
    expected_should_override = {
        c["rank_feature"]["field"] for c in bool_query_override.get("should", [])
    }
    assert "embedding_full_record.high" in expected_must_override
    assert "embedding_full_record.low" in expected_should_override


def test_event_drop_threshold_override_is_used(mock_query_tokenizer):
    # Passing drop_boost_threshold=0.0 and short_query_max_tokens=0 ensures
    # nothing is dropped even when weights are tiny.
    tokens = {f"t{i}": float(10 - i) for i in range(SHORT_QUERY_MAX_TOKENS)}
    tokens["tiny"] = 0.001
    mock_query_tokenizer.tokenize_query.return_value = tokens
    result = tokenizer_handler.lambda_handler(
        {"query": "test", "drop_boost_threshold": 0.0, "short_query_max_tokens": 0},
        {},
    )
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    all_fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert "embedding_full_record.tiny" in all_fields


# ---------------------------------------------------------------------------
# Threshold parsing: invalid override values fall back to module defaults
# ---------------------------------------------------------------------------


def test_invalid_must_boost_threshold_falls_back_to_default(mock_query_tokenizer):
    # "bad" cannot be parsed as float → MUST_BOOST_THRESHOLD (0.70) is used.
    # With high=10.0 and low=5.0, only high (>= 70% of 10) lands in must.
    mock_query_tokenizer.tokenize_query.return_value = {"high": 10.0, "low": 5.0}
    result = tokenizer_handler.lambda_handler(
        {"query": "high low", "must_boost_threshold": "bad"},
        {},
    )
    bool_query = result["query"]["bool"]
    must_fields = {c["rank_feature"]["field"] for c in bool_query.get("must", [])}
    should_fields = {c["rank_feature"]["field"] for c in bool_query.get("should", [])}
    assert "embedding_full_record.high" in must_fields
    assert "embedding_full_record.low" in should_fields


def test_invalid_drop_boost_threshold_falls_back_to_default(mock_query_tokenizer):
    # "bad" cannot be parsed as float → DROP_BOOST_THRESHOLD (0.10) is used.
    # With many tokens including a near-zero one, the near-zero token is still dropped.
    tokens = {f"t{i}": float(10 - i) for i in range(SHORT_QUERY_MAX_TOKENS)}
    tokens["near_zero"] = 0.001
    mock_query_tokenizer.tokenize_query.return_value = tokens
    result = tokenizer_handler.lambda_handler(
        {"query": "test", "drop_boost_threshold": "bad"},
        {},
    )
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    all_fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert "embedding_full_record.near_zero" not in all_fields


def test_invalid_short_query_max_tokens_falls_back_to_default(mock_query_tokenizer):
    # "bad" cannot be parsed as int → SHORT_QUERY_MAX_TOKENS is used.
    # With exactly SHORT_QUERY_MAX_TOKENS tokens, no dropping occurs.
    tokens = {f"t{i}": float(10 - i) for i in range(SHORT_QUERY_MAX_TOKENS)}
    tokens["tiny"] = 0.001
    # len == SHORT_QUERY_MAX_TOKENS + 1, so drop logic applies with the default
    mock_query_tokenizer.tokenize_query.return_value = tokens
    result = tokenizer_handler.lambda_handler(
        {"query": "test", "short_query_max_tokens": "bad"},
        {},
    )
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    all_fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert "embedding_full_record.tiny" not in all_fields


# ---------------------------------------------------------------------------
# Threshold parsing: out-of-range values are clamped
# ---------------------------------------------------------------------------


def test_must_boost_threshold_above_one_is_clamped_to_one(mock_query_tokenizer):
    # With high=10.0 and low=9.9, demonstrate that the clamping changes behavior:
    # - Default (0.70): 9.9 >= 7.0 → low goes to must
    # - Clamped to 1.0 (pass 1.5): 9.9 < 10.0 → low goes to should
    mock_query_tokenizer.tokenize_query.return_value = {"high": 10.0, "low": 9.9}

    # First: with default threshold, low should be in must
    result_default = tokenizer_handler.lambda_handler(
        {"query": "high low"},
        {},
    )
    bool_query_default = result_default["query"]["bool"]
    expected_must_default = {
        c["rank_feature"]["field"] for c in bool_query_default.get("must", [])
    }
    assert "embedding_full_record.high" in expected_must_default
    assert "embedding_full_record.low" in expected_must_default
    assert "should" not in bool_query_default

    # Second: with clamped threshold (1.5 → 1.0), low should move to should
    result_clamped = tokenizer_handler.lambda_handler(
        {"query": "high low", "must_boost_threshold": 1.5},
        {},
    )
    bool_query_clamped = result_clamped["query"]["bool"]
    expected_must_clamped = {
        c["rank_feature"]["field"] for c in bool_query_clamped.get("must", [])
    }
    expected_should_clamped = {
        c["rank_feature"]["field"] for c in bool_query_clamped.get("should", [])
    }
    assert "embedding_full_record.high" in expected_must_clamped
    assert "embedding_full_record.low" in expected_should_clamped


def test_must_boost_threshold_below_zero_is_clamped_to_zero(mock_query_tokenizer):
    # -0.5 → clamped to 0.0; must_cutoff == 0.0 so all tokens go to must.
    mock_query_tokenizer.tokenize_query.return_value = {"high": 10.0, "low": 5.0}
    result = tokenizer_handler.lambda_handler(
        {"query": "high low", "must_boost_threshold": -0.5},
        {},
    )
    bool_query = result["query"]["bool"]
    must_fields = {c["rank_feature"]["field"] for c in bool_query.get("must", [])}
    assert "embedding_full_record.high" in must_fields
    assert "embedding_full_record.low" in must_fields
    assert "should" not in bool_query


def test_drop_boost_threshold_above_one_is_clamped_to_one(mock_query_tokenizer):
    # 1.5 → clamped to 1.0; drop_cutoff == max_weight so all tokens strictly
    # below max are dropped (long query).
    tokens = {f"filler{i}": 10.0 for i in range(SHORT_QUERY_MAX_TOKENS)}
    tokens["below_max"] = 5.0
    mock_query_tokenizer.tokenize_query.return_value = tokens
    result = tokenizer_handler.lambda_handler(
        {"query": "test", "drop_boost_threshold": 1.5},
        {},
    )
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    all_fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert "embedding_full_record.below_max" not in all_fields


def test_drop_boost_threshold_below_zero_is_clamped_to_zero(mock_query_tokenizer):
    # -0.5 → clamped to 0.0; drop_cutoff == 0.0 so nothing is dropped.
    tokens = {f"t{i}": float(10 - i) for i in range(SHORT_QUERY_MAX_TOKENS)}
    tokens["tiny"] = 0.001
    mock_query_tokenizer.tokenize_query.return_value = tokens
    result = tokenizer_handler.lambda_handler(
        {"query": "test", "drop_boost_threshold": -0.5},
        {},
    )
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    all_fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert "embedding_full_record.tiny" in all_fields


def test_short_query_max_tokens_below_zero_is_clamped_to_zero(mock_query_tokenizer):
    # -1 → clamped to 0; len(tokens) > 0 is always true, so drop logic applies
    # even for a single-token query with a tiny weight.
    mock_query_tokenizer.tokenize_query.return_value = {"dominant": 10.0, "tiny": 0.001}
    result = tokenizer_handler.lambda_handler(
        {"query": "test", "short_query_max_tokens": -1},
        {},
    )
    bool_query = result["query"]["bool"]
    all_clauses = bool_query.get("must", []) + bool_query.get("should", [])
    all_fields = {c["rank_feature"]["field"] for c in all_clauses}
    assert "embedding_full_record.tiny" not in all_fields


# ---------------------------------------------------------------------------
# Integration tests — load the real tokenizer and IDF from disk
# Run only integration tests: uv run pytest -m integration
# Run all except integration tests: uv run pytest -m "not integration"
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_lambda_handler_returns_opensearch_query():
    tokenizer_handler._get_tokenizer.cache_clear()  # ensure cold start
    result = tokenizer_handler.lambda_handler({"query": "open access"}, {})
    assert "query" in result
    assert "bool" in result["query"]
    bool_query = result["query"]["bool"]
    assert "must" in bool_query or "should" in bool_query
