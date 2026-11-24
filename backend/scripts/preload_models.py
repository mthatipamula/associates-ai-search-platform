"""Download the embedding and re-ranking models at image build time.

Baking models into the image means containers start without reaching the
Hugging Face hub (no runtime internet dependency, faster cold starts, and the
exact model files are versioned with the image).
"""

import os

from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

embed_model = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
rerank_model = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")

list(TextEmbedding(model_name=embed_model).embed(["warm-up"]))
list(TextCrossEncoder(model_name=rerank_model).rerank("warm-up", ["warm-up"]))
print(f"preloaded {embed_model} and {rerank_model} into {os.environ.get('FASTEMBED_CACHE_PATH')}")
