import json
import logging
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import os

import torch
from transformers import AutoTokenizer

logger = logging.getLogger(__name__)


class QueryTokenizer:
    """Tokenizer for generating sparse query vectors for OpenSearch neural sparse search.

    Uses the OpenSearch neural sparse encoding model (doc-v3-gte) to convert query text
    into a sparse representation where each token is weighted by its IDF (Inverse Document
    Frequency) score. The resulting dict maps vocabulary tokens to float weights, suitable
    for use in OpenSearch `rank_feature` queries.
    """

    def __init__(self) -> None:
        # Load tokenizer from local path
        # Model: opensearch-neural-sparse-encoding-doc-v3-gte, stored in the repo
        # to avoid network calls at Lambda cold start
        tokenizer_path = "opensearch-project/opensearch-neural-sparse-encoding-doc-v3-gte"
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)

        # Load IDF weights from local file
        idf_path = tokenizer_path + "/idf.json"
        self.idf = self._load_idf(idf_path)

    def _load_idf(self, idf_path: str | os.PathLike[str]) -> torch.Tensor:
        """Load IDF weights from a local JSON file into a vocabulary-sized tensor.

        IDF (Inverse Document Frequency) weights down-score tokens that appear
        frequently across documents (e.g. "the", "and") and up-score rare, more
        meaningful tokens. The resulting tensor is indexed by token ID, aligned
        with the tokenizer's vocabulary.
        """
        with open(idf_path) as f:
            idf_dict = json.load(f)

        # Convert to tensor
        idf_vector = [0] * self.tokenizer.vocab_size
        for token, weight in idf_dict.items():
            token_id = cast("int", self.tokenizer.convert_tokens_to_ids(token))
            idf_vector[token_id] = weight
        return torch.tensor(idf_vector)

    def tokenize_query(self, query_text: str) -> dict[str, float]:
        """Convert query text into sparse token weights for OpenSearch rank_feature query.

        Tokenizes the input, marks which vocabulary tokens are present (known as a one-hot
        vector in machine learning), then scales each by its IDF weight. Only tokens
        present in the query with a non-zero IDF weight appear in the result. Token
        strings are vocabulary tokens (not necessarily whole words) and float values are
        their IDF-weighted scores.
        """
        feature_query = self.tokenizer(
            [query_text],
            padding=True,
            truncation=True,
            return_tensors="pt",
            return_token_type_ids=False,
        )
        input_ids = feature_query["input_ids"]

        # Create one-hot vector and apply IDF weights
        batch_size = input_ids.shape[0]
        query_vector = torch.zeros(batch_size, self.tokenizer.vocab_size)
        query_vector[torch.arange(batch_size).unsqueeze(-1), input_ids] = 1
        query_sparse_vector = query_vector * self.idf

        # Convert to dict format
        return self._sparse_vector_to_dict(query_sparse_vector[0])

    def _sparse_vector_to_dict(self, sparse_vector: torch.Tensor) -> dict[str, float]:
        """Convert a 1D sparse tensor into a dict of token strings to float weights.

        Only non-zero entries are included in the output, keeping the result compact
        and directly usable as an OpenSearch rank_feature query payload.
        """
        token_indices = torch.nonzero(sparse_vector, as_tuple=True)[0]
        non_zero_values = sparse_vector[token_indices].tolist()
        tokens = [
            cast("str", self.tokenizer.convert_ids_to_tokens(idx.item()))
            for idx in token_indices
        ]
        return dict(zip(tokens, non_zero_values, strict=False))
