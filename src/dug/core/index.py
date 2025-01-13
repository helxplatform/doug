"""
This class is used for adding documents to elastic search index
"""
import logging

from elasticsearch import Elasticsearch
import ssl

from dug.config import Config

logger = logging.getLogger('dug')


class Index:
    def __init__(self, cfg: Config, indices=None):

        if indices is None:
            indices = ['concepts_index', 'variables_index', 'kg_index']

        self._cfg = cfg
        logger.debug(f"Connecting to elasticsearch host: {self._cfg.elastic_host} at port: {self._cfg.elastic_port}")

        self.indices = indices
        self.hosts = [{'host': self._cfg.elastic_host, 'port': self._cfg.elastic_port, 'scheme': self._cfg.elastic_scheme}]

        logger.debug(f"Authenticating as user {self._cfg.elastic_username} to host:{self.hosts}")
        if self._cfg.elastic_scheme == "https":
            ssl_context = ssl.create_default_context(
                cafile=self._cfg.elastic_ca_path
            )
            self.es = Elasticsearch(
                hosts=self.hosts,
                basic_auth=(self._cfg.elastic_username, self._cfg.elastic_password),
                ssl_context=ssl_context)
        else:
            self.es = Elasticsearch(
                hosts=self.hosts,
                basic_auth=(self._cfg.elastic_username, self._cfg.elastic_password))
        self.replicas = self.get_es_node_count()

        if self.es.ping():
            logger.info('connected to elasticsearch')
            self.init_indices()
        else:
            print(f"Unable to connect to elasticsearch at {self._cfg.elastic_host}:{self._cfg.elastic_port}")
            logger.error(f"Unable to connect to elasticsearch at {self._cfg.elastic_host}:{self._cfg.elastic_port}")
            raise SearchException(
                message='failed to connect to elasticsearch',
                details=f"connecting to host {self._cfg.elastic_host} and port {self._cfg.elastic_port}")
        
    def get_es_node_count(self):
        return self.es.nodes.info()["_nodes"]["total"]
        

    def init_indices(self):
        # The concepts and variable indices include an analyzer that utilizes the english
        # stopword facility from elastic search.  We also instruct each of the text mappings
        # to use this analyzer. Note that we have not upgraded the kg index, because the fields
        # in that index are primarily dynamic. We could eventually either add mappings so that
        # the fields are no longer dynamic or we could use the dynamic template capabilities
        # described in
        # https://www.elastic.co/guide/en/elasticsearch/reference/current/dynamic-templates.html

        kg_index = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": self.replicas
            },
            "mappings": {
                "properties": {
                    "name": {
                        "type": "text"
                    },
                    "type": {
                        "type": "text"
                    }
                }
            }
        }
        concepts_index = {
            "settings": {
                "index.mapping.coerce": "false",
                "number_of_shards": 1,
                "number_of_replicas": self.replicas,
                "analysis": {
                    "analyzer": {
                        "std_with_stopwords": {
                            "type": "standard",
                            "stopwords": "_english_"
                        }
                    }
                }
            },
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "id": {"type": "text", "analyzer": "std_with_stopwords",
                           "fields": {"keyword": {"type": "keyword"}}},
                    "name": {"type": "text", "analyzer": "std_with_stopwords"},
                    "description": {"type": "text", "analyzer": "std_with_stopwords"},
                    "type": {"type": "keyword"},
                    "search_terms": {"type": "text", "analyzer": "std_with_stopwords"},
                    "identifiers": {
                        "properties": {
                            "id": {"type": "text", "analyzer": "std_with_stopwords",
                                   "fields": {"keyword": {"type": "keyword"}}},
                            "label": {"type": "text", "analyzer": "std_with_stopwords"},
                            "equivalent_identifiers": {"type": "keyword"},
                            "type": {"type": "keyword"},
                            "synonyms": {"type": "text", "analyzer": "std_with_stopwords"}
                        }
                    },
                    "optional_terms": {"type": "text", "analyzer": "std_with_stopwords"},
                    "concept_action": {"type": "text", "analyzer": "std_with_stopwords"}
                }
            }
        }
        variables_index = {
            "settings": {
                "index.mapping.coerce": "false",
                "number_of_shards": 1,
                "number_of_replicas": self.replicas,
                "analysis": {
                    "analyzer": {
                        "std_with_stopwords": {
                            "type": "standard",
                            "stopwords": "_english_"
                        }
                    }
                }
            },
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "element_id": {"type": "text", "analyzer": "std_with_stopwords",
                                   "fields": {"keyword": {"type": "keyword"}}},
                    "element_name": {"type": "text", "analyzer": "std_with_stopwords"},
                    "element_desc": {"type": "text", "analyzer": "std_with_stopwords"},
                    "element_action": {"type": "text", "analyzer": "std_with_stopwords"},
                    "search_terms": {"type": "text", "analyzer": "std_with_stopwords"},
                    "optional_terms": {"type": "text", "analyzer": "std_with_stopwords"},
                    "identifiers": {"type": "keyword"},
                    "collection_id": {"type": "text", "analyzer": "std_with_stopwords",
                                      "fields": {"keyword": {"type": "keyword"}}},
                    "collection_name": {"type": "text", "analyzer": "std_with_stopwords"},
                    "collection_desc": {"type": "text", "analyzer": "std_with_stopwords"},
                    "collection_action": {"type": "text", "analyzer": "std_with_stopwords"},
                    "data_type": {"type": "text", "analyzer": "std_with_stopwords",
                                  "fields": {"keyword": {"type": "keyword"}}},
                    "metadata": {
                        "type": "object",
                        "dynamic": True
                    }
                    # typed as keyword for bucket aggs
                }
            }
        }

        settings = {
            'kg_index': kg_index,
            'concepts_index': concepts_index,
            'variables_index': variables_index,
        }

        logger.info(f"creating indices")
        logger.debug(self.indices)
        for index in self.indices:
            try:
                if self.es.indices.exists(index=index):
                    # if index exists check if replication is good 
                    index_replicas = self.es.indices.get_settings(index=index)[index]["settings"]["index"]["number_of_replicas"]
                    if index_replicas != self.replicas:
                        self.es.indices.put_settings(index=index, body={"number_of_replicas": (self.replicas - 1) or 1 })
                        self.es.indices.refresh(index=index)
                    logger.info(f"Ignoring index {index} which already exists.")
                else:
                    result = self.es.indices.create(
                        index=index,
                        body=settings[index],
                        ignore=400)
                    logger.info(f"result created index {index}: {result}")
            except Exception as e:
                logger.error(f"exception: {e}")
                raise e

    def index_doc(self, index, doc, doc_id):
        self.es.index(
            index=index,
            id=doc_id,
            body=doc)

    def update_doc(self, index, doc, doc_id):
        self.es.update(
            index=index,
            id=doc_id,
            body=doc
        )

    def index_concept(self, concept, index):
        # Don't re-index if already in index
        if self.es.exists(index=index, id=concept.id):
            return
        """ Index the document. """
        self.index_doc(
            index=index,
            doc=concept.get_searchable_dict(),
            doc_id=concept.id)

    def index_element(self, elem, index):
        if not self.es.exists(index=index, id=elem.get_id()):
            # If the element doesn't exist, add it directly
            self.index_doc(
                index=index,
                doc=elem.get_searchable_dict(),
                doc_id=elem.get_id())
        else:
            # Otherwise update to add any new identifiers that weren't there last time around
            results = self.es.get(index=index, id=elem.get_id())
            identifiers = results['_source']['identifiers'] + list(elem.concepts.keys())
            doc = {"doc": {}}
            doc['doc']['identifiers'] = list(set(identifiers))
            self.update_doc(index=index, doc=doc, doc_id=elem.id)

    def index_kg_answer(self, concept_id, kg_answer, index, id_suffix=None):

        # Get search targets by extracting names/synonyms from non-curie nodes in answer knoweldge graph
        search_targets = kg_answer.get_node_names(include_curie=False)
        search_targets += kg_answer.get_node_synonyms(include_curie=False)

        # Create the Doc
        doc = {
            'concept_id': concept_id,
            'search_targets': list(set(search_targets)),
            'knowledge_graph': kg_answer.get_kg()
        }

        # Create unique ID
        logger.debug("Indexing TranQL query answer...")
        id_suffix = list(kg_answer.nodes.keys()) if id_suffix is None else id_suffix
        unique_doc_id = f"{concept_id}_{id_suffix}"

        """ Index the document. """
        self.index_doc(
            index=index,
            doc=doc,
            doc_id=unique_doc_id)

class SearchException(Exception):
    def __init__(self, message, details):
        self.message = message
        self.details = details