import os
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest
import pytest_asyncio

from dug.core.index import Index, SearchException
from dug.config import Config

default_indices = ["concepts_index", "variables_index", "kg_index"]

host = "localhost"
port = 9200
username = "elastic"
password = "hunter2"
nboost_host = "localhost"
hosts = [{"host": host, "port": port, "scheme": "https"}]


class MockEsNode:
    def info():
        return {"_nodes": {"total": 1}}


@dataclass
class MockIndex:
    settings: dict
    mappings: dict
    values: dict = field(default_factory=dict)

    def index(self, id, body):
        self.values[id] = body

    def update(self, id, body):
        return self.index(id, body)

    def get(self, id):
        return self.values.get(id)

    def count(self, body):
        return len(self.values)


class MockIndices:
    def __init__(self):
        self._indices = {}
        self.call_count = 0
        self.number_of_replicas = 1

    def exists(self, index):
        return index in self._indices

    def create(self, index, body, **_kwargs):
        self.call_count += 1
        self._indices[index] = MockIndex(**body)

    def get_index(self, index) -> MockIndex:
        return self._indices.get(index)

    def get_settings(self, index):
        index_schema = {"settings": {"index": {"number_of_replicas": self.number_of_replicas}}}
        settings = {
            "kg_index": index_schema,
            "concepts_index": index_schema,
            "variables_index": index_schema,
        }
        return settings

class MockElastic:
    def __init__(self, indices: MockIndices):
        self.indices = indices
        self._up = True
        self.nodes = MockEsNode

    def index(self, index, id=None, body=None):
        self.indices.get_index(index).index(id, body)

    def update(self, index, id=None, body=None):
        self.indices.get_index(index).update(id, body)

    def ping(self):
        return self._up

    def connect(self):
        self._up = True

    def disconnect(self):
        self._up = False

    def count(self, body, index):
        return {"count": self.indices.get_index(index).count(body)}

    def search(self, index, body, **kwargs):
        values = self.indices.get_index(index).values
        return {"results": {k: v for k, v in values.items() if body in v}}


@pytest_asyncio.fixture
def elastic():
    with patch("dug.core.index.Elasticsearch") as es_class:
        es_instance = MockElastic(indices=MockIndices())
        es_class.return_value = es_instance
        yield es_instance


def test_init(elastic):
    cfg = Config(
        elastic_host="localhost",
        elastic_username="elastic",
        elastic_password="hunter2",
        nboost_host="localhost",
        elastic_scheme="https"
    )

    search = Index(cfg)

    assert search.indices == default_indices
    assert search.hosts == hosts
    assert search.es is elastic


def test_init_no_ping(elastic):
    elastic.disconnect()
    with pytest.raises(SearchException):
        _search = Index(Config.from_env())


@pytest.mark.asyncio
async def test_init_indices(elastic):
    search = Index(Config.from_env())
    assert elastic.indices.call_count == 3

    # Should take no action if called again
    search.init_indices()
    assert elastic.indices.call_count == 3


def test_index_doc(elastic: MockElastic):
    search = Index(Config.from_env())

    assert len(elastic.indices.get_index("concepts_index").values) == 0
    search.index_doc("concepts_index", {"name": "sample"}, "ID:1")
    assert len(elastic.indices.get_index("concepts_index").values) == 1
    assert elastic.indices.get_index("concepts_index").get("ID:1") == {"name": "sample"}


def test_update_doc(elastic: MockElastic):
    search = Index(Config.from_env())

    search.index_doc("concepts_index", {"name": "sample"}, "ID:1")
    search.update_doc("concepts_index", {"name": "new value!"}, "ID:1")
    assert elastic.indices.get_index("concepts_index").get("ID:1") == {
        "name": "new value!"
    }
