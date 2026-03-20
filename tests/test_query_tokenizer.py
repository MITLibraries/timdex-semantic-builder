import json
from unittest.mock import MagicMock, mock_open, patch

import pytest
import torch

from lambdas.query_tokenizer import QueryTokenizer

VOCAB_SIZE = 100
MOCK_IDF = {"hello": 1.5, "world": 2.0}
# token ids for "hello" and "world" in mock vocab
HELLO_ID = 5
WORLD_ID = 10


def make_mock_tokenizer():
    mock_tokenizer = MagicMock()
    mock_tokenizer.vocab_size = VOCAB_SIZE
    mock_tokenizer.convert_tokens_to_ids.side_effect = lambda t: (
        HELLO_ID if t == "hello" else WORLD_ID
    )
    mock_tokenizer.convert_ids_to_tokens.side_effect = lambda ids: [
        "hello" if i == HELLO_ID else "world" for i in ids
    ]
    return mock_tokenizer


@pytest.fixture
def query_tokenizer():
    mock_tokenizer = make_mock_tokenizer()
    with (
        patch(
            "lambdas.query_tokenizer.AutoTokenizer.from_pretrained",
            return_value=mock_tokenizer,
        ),
        patch("builtins.open", mock_open(read_data=json.dumps(MOCK_IDF))),
    ):
        return QueryTokenizer()


def test_idf_loaded_as_tensor(query_tokenizer):
    assert isinstance(query_tokenizer.idf, torch.Tensor)
    assert query_tokenizer.idf.shape[0] == VOCAB_SIZE
    assert query_tokenizer.idf[HELLO_ID].item() == pytest.approx(1.5)
    assert query_tokenizer.idf[WORLD_ID].item() == pytest.approx(2.0)


def test_tokenize_query_returns_dict(query_tokenizer):
    # Simulate tokenizer returning input_ids containing HELLO_ID and WORLD_ID
    query_tokenizer.tokenizer.return_value = {
        "input_ids": torch.tensor([[HELLO_ID, WORLD_ID]])
    }
    result = query_tokenizer.tokenize_query("hello world")
    assert isinstance(result, dict)
    assert len(result) > 0


def test_tokenize_query_weights_are_floats(query_tokenizer):
    query_tokenizer.tokenizer.return_value = {
        "input_ids": torch.tensor([[HELLO_ID, WORLD_ID]])
    }
    result = query_tokenizer.tokenize_query("hello world")
    for weight in result.values():
        assert isinstance(weight, float)


def test_sparse_vector_to_dict_maps_tokens_to_weights(query_tokenizer):
    sparse = torch.zeros(VOCAB_SIZE)
    sparse[HELLO_ID] = 1.5
    sparse[WORLD_ID] = 2.0
    result = query_tokenizer._sparse_vector_to_dict(sparse)
    assert result == {"hello": pytest.approx(1.5), "world": pytest.approx(2.0)}


def test_sparse_vector_to_dict_excludes_zero_weights(query_tokenizer):
    sparse = torch.zeros(VOCAB_SIZE)
    sparse[HELLO_ID] = 1.5
    result = query_tokenizer._sparse_vector_to_dict(sparse)
    assert "world" not in result


def test_tokenize_query_returns_correct_weights(query_tokenizer):
    query_tokenizer.tokenizer.return_value = {
        "input_ids": torch.tensor([[HELLO_ID, WORLD_ID]])
    }
    result = query_tokenizer.tokenize_query("hello world")
    assert result == {"hello": pytest.approx(1.5), "world": pytest.approx(2.0)}


def test_tokenize_query_excludes_tokens_not_in_idf(query_tokenizer):
    # ID 20 is not in MOCK_IDF so its IDF weight is 0; it should be absent from result
    query_tokenizer.tokenizer.convert_ids_to_tokens.side_effect = lambda ids: [
        "hello" if i == HELLO_ID else "unknown" for i in ids
    ]
    query_tokenizer.tokenizer.return_value = {"input_ids": torch.tensor([[HELLO_ID, 20]])}
    result = query_tokenizer.tokenize_query("hello unknown")
    assert "hello" in result
    assert "unknown" not in result


def test_init_raises_filenotfounderror_when_tokenizer_path_missing():
    """Test that FileNotFoundError is raised when tokenizer_path doesn't exist."""
    with (
        patch("pathlib.Path.exists", return_value=False),
        pytest.raises(FileNotFoundError, match="Tokenizer path not found"),
    ):
        QueryTokenizer()


def test_init_raises_filenotfounderror_with_correct_path_message():
    """Test that FileNotFoundError message includes the missing path."""
    missing_path = "opensearch-project/opensearch-neural-sparse-encoding-doc-v3-gte"
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError) as exc_info:
            QueryTokenizer()
        assert missing_path in str(exc_info.value)


def test_load_idf_raises_filenotfounderror_when_idf_file_missing():
    """Test that FileNotFoundError is raised when IDF file doesn't exist."""
    mock_tokenizer = make_mock_tokenizer()
    with (
        patch(
            "lambdas.query_tokenizer.AutoTokenizer.from_pretrained",
            return_value=mock_tokenizer,
        ),
        patch("pathlib.Path.exists", return_value=True),
        patch("builtins.open", side_effect=FileNotFoundError()),
        pytest.raises(FileNotFoundError),
    ):
        QueryTokenizer()


# ---------------------------------------------------------------------------
# Integration tests — load the real tokenizer and IDF from disk
# Run only integration tests: uv run pytest -m integration
# Run all except integration tests: uv run pytest -m "not integration"
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_tokenize_query_returns_nonempty_dict():
    """Real tokenizer and IDF: tokenize_query returns a non-empty dict."""
    qt = QueryTokenizer()
    result = qt.tokenize_query("machine learning")
    assert isinstance(result, dict)
    assert len(result) > 0


@pytest.mark.integration
def test_integration_tokenize_query_values_are_positive_floats():
    """Real tokenizer and IDF: all weights are positive floats."""
    qt = QueryTokenizer()
    result = qt.tokenize_query("machine learning")
    for token, weight in result.items():
        assert isinstance(token, str), f"Expected str key, got {type(token)}"
        assert isinstance(weight, float), f"Expected float weight, got {type(weight)}"
        assert weight > 0, f"Expected positive weight for {token!r}, got {weight}"


@pytest.mark.integration
def test_integration_tokenize_query_deterministic():
    """Real tokenizer and IDF: same input always produces the same output."""
    qt = QueryTokenizer()
    result_a = qt.tokenize_query("open access repositories")
    result_b = qt.tokenize_query("open access repositories")
    assert result_a == result_b
