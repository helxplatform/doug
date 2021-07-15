import json
import logging

import requests
from elasticsearch import Elasticsearch

from dug.config import Config

logger = logging.getLogger('dug')


class Search:
    """ Search -
    1. Lexical fuzziness; (a) misspellings - a function of elastic.
    2. Fuzzy ontologically;
       (a) expand based on core queries
         * phenotype->study
         * phenotype->disease->study
         * disease->study
         * disease->phenotype->study
    """

    def __init__(self, cfg: Config, indices=None):

        if indices is None:
            indices = ['concepts_index', 'variables_index', 'kg_index']

        self._cfg = cfg
        logger.debug(f"Connecting to elasticsearch host: {self._cfg.elastic_host} at port: {self._cfg.elastic_port}")

        self.indices = indices
        self.hosts = [{'host': self._cfg.elastic_host, 'port': self._cfg.elastic_port}]

        logger.debug(f"Authenticating as user {self._cfg.elastic_username} to host:{self.hosts}")

        self.es = Elasticsearch(hosts=self.hosts,
                                http_auth=(self._cfg.elastic_username, self._cfg.elastic_password))

        if self.es.ping():
            logger.info('connected to elasticsearch')
            self.init_indices()
        else:
            print(f"Unable to connect to elasticsearch at {self._cfg.elastic_host}:{self._cfg.elastic_port}")
            logger.error(f"Unable to connect to elasticsearch at {self._cfg.elastic_host}:{self._cfg.elastic_port}")
            raise SearchException(
                message='failed to connect to elasticsearch',
                details=f"connecting to host {self._cfg.elastic_host} and port {self._cfg.elastic_port}")

    def init_indices(self):
        kg_index = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
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
                "number_of_replicas": 0
            },
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "id": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "name": {"type": "text"},
                    "description": {"type": "text"},
                    "type": {"type": "keyword"},
                    "search_terms": {"type": "text"},
                    "identifiers": {
                        "properties": {
                            "id": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                            "label": {"type": "text"},
                            "equivalent_identifiers": {"type": "keyword"},
                            "type": {"type": "keyword"},
                            "synonyms": {"type": "text"}
                        }
                    },
                    "optional_terms": {"type": "text"},
                    "concept_action": {"type": "text"}
                }
            }
        }
        variables_index = {
            "settings": {
                "index.mapping.coerce": "false",
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "element_id": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "element_name": {"type": "text"},
                    "element_desc": {"type": "text"},
                    "element_action": {"type": "text"},
                    "search_terms": {"type": "text"},
                    "optional_terms": {"type": "text"},
                    "identifiers": {"type": "keyword"},
                    "collection_id": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "collection_name": {"type": "text"},
                    "collection_desc": {"type": "text"},
                    "collection_action": {"type": "text"},
                    "data_type": {"type": "text", "fields": {"keyword": {"type": "keyword"}}}
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
        #optterms = doc['optional_terms']
        #if len(optterms) == 0:
        #    del doc['optional_terms']
        #    print('deleted optional_terms')
        try:
            self.es.index(
                index=index,
                id=doc_id,
                body=doc)
        except Exception as e:
                print('doc:',doc)
                logger.error(f"exception: {e}")
                raise e

    def update_doc(self, index, doc, doc_id):
        self.es.update(
            index=index,
            id=doc_id,
            body=doc
        )

    def search_concepts(self, index, query, offset=0, size=None, fuzziness=1, prefix_length=3):
        """
        Changed to a long boolean match query to optimize search results
        """
        query = {
            "bool": {
                "should": [
                    {
                        "match_phrase": {
                            "name": {
                                "query": query,
                                "boost": 10
                            }
                        }
                    },
                    {
                        "match_phrase": {
                            "description": {
                                "query": query,
                                "boost": 6
                            }
                        }
                    },
                    {
                        "match_phrase": {
                            "search_terms": {
                                "query": query,
                                "boost": 8
                            }
                        }
                    },
                    {
                        "match": {
                            "name": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "operator": "and",
                                "boost": 4
                            }
                        }
                    },
                    {
                        "match": {
                            "search_terms": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "operator": "and",
                                "boost": 5
                            }
                        }
                    },
                    {
                        "match": {
                            "description": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "operator": "and",
                                "boost": 3
                            }
                        }
                    },
                    {
                        "match": {
                            "description": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "boost": 2
                            }
                        }
                    },
                    {
                        "match": {
                            "search_terms": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "boost": 1
                            }
                        }
                    },
                    {
                        "match": {
                            "optional_terms": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length
                            }
                        }
                    }
                ]
            }
        }
        body = json.dumps({'query': query})
        total_items = self.es.count(body=body, index=index)
        search_results = self.es.search(
            index=index,
            body=body,
            filter_path=['hits.hits._id', 'hits.hits._type', 'hits.hits._source'],
            from_=offset,
            size=size
        )
        search_results.update({'total_items': total_items['count']})
        return search_results

    def search_variables(self, index, concept="", query="", size=None, data_type=None, offset=0, fuzziness=1,
                         prefix_length=3):
        """
        In variable seach, the concept MUST match one of the indentifiers in the list
        The query can match search_terms (hence, "should") for ranking.

        Results Return
        The search result is returned in JSON format {collection_id:[elements]}

        Filter
        If a data_type is passed in, the result will be filtered to only contain
        the passed-in data type.
        """
        query = {
            'bool': {
                'should': {
                    "match": {
                        "identifiers": concept
                    }
                },
                'should': [
                    {
                        "match_phrase": {
                            "element_name": {
                                "query": query,
                                "boost": 10
                            }
                        }
                    },
                    {
                        "match_phrase": {
                            "element_desc": {
                                "query": query,
                                "boost": 6
                            }
                        }
                    },
                    {
                        "match_phrase": {
                            "search_terms": {
                                "query": query,
                                "boost": 8
                            }
                        }
                    },
                    {
                        "match": {
                            "element_name": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "operator": "and",
                                "boost": 4
                            }
                        }
                    },
                    {
                        "match": {
                            "search_terms": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "operator": "and",
                                "boost": 5
                            }
                        }
                    },
                    {
                        "match": {
                            "element_desc": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "operator": "and",
                                "boost": 3
                            }
                        }
                    },
                    {
                        "match": {
                            "element_desc": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "boost": 2
                            }
                        }
                    },
                    {
                        "match": {
                            "element_name": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "boost": 2
                            }
                        }
                    },
                    {
                        "match": {
                            "search_terms": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length,
                                "boost": 1
                            }
                        }
                    },
                    {
                        "match": {
                            "optional_terms": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "prefix_length": prefix_length
                            }
                        }
                    }
                ]
            }
        }

        if concept:
            query['bool']['must'] = {
                "match": {
                        "identifiers": concept
                }
            }
        
        body = json.dumps({'query': query})
        search_results = self.es.search(
            index=index,
            body=body,
            filter_path=['hits.hits._id', 'hits.hits._type', 'hits.hits._source'],
            from_=offset,
            size=size
        )

        # Reformat Results
        new_results = {}
        for elem in search_results['hits']['hits']:
            elem_s = elem['_source']
            elem_type = elem_s['data_type']
            if elem_type not in new_results:
                new_results[elem_type] = {}

            elem_id = elem_s['element_id']
            coll_id = elem_s['collection_id']
            elem_info = {
                "description": elem_s['element_desc'],
                "e_link": elem_s['element_action'],
                "id": elem_id,
                "name": elem_s['element_name']
            }

            # Case: collection not in dictionary for given data_type
            if coll_id not in new_results[elem_type]:
                # initialize document
                doc = {}

                # add information
                doc['c_id'] = coll_id
                doc['c_link'] = elem_s['collection_action']
                doc['c_name'] = elem_s['collection_name']
                doc['elements'] = [elem_info]

                # save document
                new_results[elem_type][coll_id] = doc

            # Case: collection already in dictionary for given element_type; append elem_info.  Assumes no duplicate elements
            else:
                new_results[elem_type][coll_id]['elements'].append(elem_info)

        # Flatten dicts to list
        for i in new_results:
            new_results[i] = list(new_results[i].values())

        # Return results
        if bool(data_type):
            if data_type in new_results:
                new_results = new_results[data_type]
            else:
                new_results = {}
        return new_results

    def agg_data_type(self, index, size=0):
        """
        In variable seach, the concept MUST match one of the indentifiers in the list
        The query can match search_terms (hence, "should") for ranking.
        """
        aggs = {
            "data_type": {
                "terms": {
                    "field": "data_type.keyword",
                    "size": 100
                }
            }
        }
        body = json.dumps({'aggs': aggs})

        search_results = self.es.search(
            index=index,
            body=body,
            size=size
        )
        data_type_list = [data_type['key'] for data_type in search_results['aggregations']['data_type']['buckets']]
        search_results.update({'data type list': data_type_list})
        return data_type_list

    def search_kg(self, index, unique_id, query, offset=0, size=None, fuzziness=1, prefix_length=3):
        """
        In knowledge graph search seach, the concept MUST match the unique ID
        The query MUST match search_targets.  The updated query allows for
        fuzzy matching and for the default OR behavior for the query.
        """
        query = {
            "bool": {
                "must": [
                    {"term": {
                        "concept_id.keyword": unique_id
                    }
                    },
                    {'query_string': {
                        "query": query,
                        "fuzziness": fuzziness,
                        "fuzzy_prefix_length": prefix_length,
                        "default_field": "search_targets"
                    }
                    }
                ]
            }
        }
        body = json.dumps({'query': query})
        total_items = self.es.count(body=body, index=index)
        search_results = self.es.search(
            index=index,
            body=body,
            filter_path=['hits.hits._id', 'hits.hits._type', 'hits.hits._source'],
            from_=offset,
            size=size
        )
        search_results.update({'total_items': total_items['count']})
        return search_results

    def search_nboost(self, index, query, offset=0, size=10, fuzziness=1):
        """
        Query type is now 'query_string'.
        query searches multiple fields
        if search terms are surrounded in quotes, looks for exact matches in any of the fields
        AND/OR operators are natively supported by elasticesarch queries
        """
        nboost_query = {
            'nboost': {
                'uhost': f"{self._cfg.elastic_username}:{self._cfg.elastic_password}@{self._cfg.elastic_host}",
                'uport': self._cfg.elastic_port,
                'cvalues_path': '_source.description',
                'query_path': 'body.query.query_string.query',
                'size': size,
                'from': offset,
                'default_topk': size
            },
            'query': {
                'query_string': {
                    'query': query,
                    'fuzziness': fuzziness,
                    'fields': ['name', 'description', 'instructions', 'search_targets', 'optional_targets'],
                    'quote_field_suffix': ".exact"
                }
            }
        }

        return requests.post(url=f"http://{self._cfg.nboost_host}:{self._cfg.nboost_port}/{index}/_search", json=nboost_query).json()

    def index_concept(self, concept, index):
        # Don't re-index if already in index
        if self.es.exists(index, concept.id):
            return
        """ Index the document. """
        self.index_doc(
            index=index,
            doc=concept.get_searchable_dict(),
            doc_id=concept.id)

    def index_element(self, elem, index):
        if not self.es.exists(index, elem.id):
            # If the element doesn't exist, add it directly
            self.index_doc(
                index=index,
                doc=elem.get_searchable_dict(),
                doc_id=elem.id)
        else:
            # Otherwise update to add any new identifiers that weren't there last time around
            results = self.es.get(index, elem.id)
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