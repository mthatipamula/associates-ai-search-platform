from __future__ import annotations

from functools import lru_cache

from elasticsearch import Elasticsearch

from .config import settings


@lru_cache(maxsize=1)
def get_es() -> Elasticsearch:
    kwargs: dict = {"request_timeout": 30, "retry_on_timeout": True, "max_retries": 3}
    if settings.es_api_key:
        kwargs["api_key"] = settings.es_api_key
    return Elasticsearch(settings.es_url, **kwargs)
