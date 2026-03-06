from unittest.mock import MagicMock, patch

import pytest

from lambdas import tokenizer_handler


@pytest.fixture
def mock_query_tokenizer():
    with patch("lambdas.tokenizer_handler.QueryTokenizer") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


def test_returns_opensearch_query_structure(mock_query_tokenizer):
    mock_query_tokenizer.tokenize_query.return_value = {"hello": 1.5, "world": 2.0}
    result = tokenizer_handler.lambda_handler({"query": "hello world"}, {})
    assert "query" in result
    assert "bool" in result["query"]
    assert "should" in result["query"]["bool"]


def test_opensearch_query_contains_rank_features(mock_query_tokenizer):
    mock_query_tokenizer.tokenize_query.return_value = {"hello": 1.5}
    result = tokenizer_handler.lambda_handler({"query": "hello"}, {})
    should_clauses = result["query"]["bool"]["should"]
    assert len(should_clauses) == 1
    assert should_clauses[0]["rank_feature"]["field"] == "embedding_full_record.hello"
    assert should_clauses[0]["rank_feature"]["boost"] == 1.5


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
    should_clauses = result["query"]["bool"]["should"]
    fields = {c["rank_feature"]["field"] for c in should_clauses}
    assert fields == {"embedding_full_record.foo", "embedding_full_record.bar"}


def test_tokenize_query_called_with_correct_query(mock_query_tokenizer):
    mock_query_tokenizer.tokenize_query.return_value = {"fakedata": 1.5}
    tokenizer_handler.lambda_handler({"query": "hello world"}, {})
    mock_query_tokenizer.tokenize_query.assert_called_once_with("hello world")


def test_returns_error_for_whitespace_only_query(mock_query_tokenizer):
    result = tokenizer_handler.lambda_handler({"query": "   "}, {})
    assert result == {"error": "Query is required in the event payload."}
    mock_query_tokenizer.tokenize_query.assert_not_called()
