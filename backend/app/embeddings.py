"""Pluggable text embedders.

local   - fastembed (ONNX runtime, CPU). No GPU or PyTorch needed.
bedrock - Amazon Titan Text Embeddings v2 via boto3 (the AWS-native option).
hash    - deterministic feature hashing; no model, used by tests/CI only. It
          captures word overlap, not meaning, so do not judge vector search
          quality with it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from typing import Protocol, Sequence

from .config import settings

# bge models are trained with an instruction prefix on the *query* side only.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    dims: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashEmbedder:
    def __init__(self, dims: int):
        self.dims = dims

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dims
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for tok in tokens:
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % self.dims] += 1.0 if (h >> 8) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FastEmbedder:
    def __init__(self, model: str, dims: int):
        from fastembed import TextEmbedding  # imported lazily: heavy

        self._model = TextEmbedding(model_name=model)
        self._is_bge = "bge" in model.lower()
        self.dims = dims

    def embed_documents(self, texts):
        return [v.tolist() for v in self._model.embed(list(texts), batch_size=64)]

    def embed_query(self, text):
        q = BGE_QUERY_PREFIX + text if self._is_bge else text
        return next(iter(self._model.embed([q]))).tolist()


class BedrockTitanEmbedder:
    MODEL_ID = "amazon.titan-embed-text-v2:0"

    def __init__(self, dims: int, region: str):
        import boto3

        if dims not in (256, 512, 1024):
            raise ValueError("Titan v2 supports 256, 512 or 1024 dims; set EMBED_DIMS accordingly")
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self.dims = dims

    def _one(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text, "dimensions": self.dims, "normalize": True})
        resp = self._client.invoke_model(modelId=self.MODEL_ID, body=body)
        return json.loads(resp["body"].read())["embedding"]

    def embed_documents(self, texts):
        # Titan v2 is one text per call; at 117k docs use Bedrock batch
        # inference (S3 in / S3 out) instead of a synchronous loop.
        return [self._one(t) for t in texts]

    def embed_query(self, text):
        return self._one(text)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    p = settings.embed_provider
    if p == "hash":
        return HashEmbedder(settings.embed_dims)
    if p == "bedrock":
        return BedrockTitanEmbedder(settings.embed_dims, settings.aws_region)
    if p == "local":
        return FastEmbedder(settings.embed_model, settings.embed_dims)
    raise ValueError(f"unknown EMBED_PROVIDER {p!r}")
