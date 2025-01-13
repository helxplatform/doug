"""Implements search methods using async interfaces"""
import logging
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_scan
import ssl,json
from dug.config import Config


logger = logging.getLogger('dug')


class SearchException(Exception):
    def __init__(self, message, details):
        self.message = message
        self.details = details


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
        logger.debug(f"Connecting to elasticsearch host: "
                     f"{self._cfg.elastic_host} at port: "
                     f"{self._cfg.elastic_port}")

        self.indices = indices
        self.hosts = [{'host': self._cfg.elastic_host,
                       'port': self._cfg.elastic_port,
                       'scheme': self._cfg.elastic_scheme}]

        logger.debug(f"Authenticating as user "
                     f"{self._cfg.elastic_username} "
                     f"to host:{self.hosts}")
        if self._cfg.elastic_scheme == "https":
            ssl_context = ssl.create_default_context(
                cafile=self._cfg.elastic_ca_path
            )
            self.es = AsyncElasticsearch(hosts=self.hosts,
                                     basic_auth=(self._cfg.elastic_username,
                                                self._cfg.elastic_password),
                                                ssl_context=ssl_context)
        else:
            self.es = AsyncElasticsearch(hosts=self.hosts,
                                     basic_auth=(self._cfg.elastic_username,
                                                self._cfg.elastic_password))

    async def dump_concepts(self, index, query={}, size=None,
                            fuzziness=1, prefix_length=3):
        """
        Get everything from concept index
        """
        query = {
            "match_all": {}
        }
        body = {"query": query}
        await self.es.ping()
        total_items = await self.es.count(body=body, index=index)
        counter = 0
        all_docs = []
        async for doc in async_scan(
                client=self.es,
                query=body,
                index=index
        ):
            if counter == size and size != 0:
                break
            counter += 1
            all_docs.append(doc)
        return {
            "status": "success",
            "result": {
                "hits": {
                    "hits": all_docs
                },
                "total_items": total_items
            },
            "message": "Search result"
        }

    async def agg_data_type(self):
        aggs = {
            "data_type": {
                "terms": {
                    "field": "data_type.keyword",
                }
            }
        }

        body = {'aggs': aggs}
        results = await self.es.search(
            index="variables_index",
            body=body
        )
        data_type_list = [data_type['key'] for data_type in
                          results['aggregations']['data_type']['buckets']]
        results.update({'data type list': data_type_list})
        return data_type_list

    @staticmethod
    def _get_concepts_query(query, fuzziness=1, prefix_length=3):
        "Static data structure populator, pulled for easier testing"
        query_object = {
            "query" : {
                "bool": {
                    "filter": {
                        "bool": {
                            "must": [
                                {"wildcard": {"description": "?*"}},
                                {"wildcard": {"name": "?*"}}
                            ]
                        }
                    },
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
                    ],
                    "minimum_should_match": 1,
                }
            }
        }
        return query_object
    
    def is_simple_search_query(self, query):
        return "*" in query or "\"" in query or "+" in query or "-" in query

    async def search_concepts(self, query, offset=0, size=None, types=None,
                              **kwargs):
        """
        Changed to a long boolean match query to optimize search results
        """
        if self.is_simple_search_query(query):
            search_body = self.get_simple_concept_search_query(query)
        else:
            search_body = self._get_concepts_query(query, **kwargs)
        # Get aggregated counts of biolink types
        search_body['aggs'] = {'type-count': {'terms': {'field': 'type'}}}
        if isinstance(types, list):
            search_body['post_filter'] = {
                "bool": {
                    "should": [
                        {'term': {'type': {'value': t}}} for t in types
                    ],
                    "minimum_should_match": 1
                }
            }
        search_results = await self.es.search(
            index="concepts_index",
            body=search_body,
            filter_path=['hits.hits._id', 'hits.hits._type',
                         'hits.hits._source', 'hits.hits._score',
                         'hits.hits._explanation', 'aggregations'],
            from_=offset,
            size=size,
            explain=True
        )
        # Aggs/post_filter aren't supported by count
        del search_body["aggs"]
        if "post_filter" in search_body:
            # We'll move the post_filter into the actual filter
            search_body["query"]["bool"]["filter"]["bool"].update(
                search_body["post_filter"]["bool"]
            )
            del search_body["post_filter"]
        total_items = await self.es.count(
            body=search_body,
            index="concepts_index"
        )

        # Simplify the data structure we get from aggregations to put into the
        # return value. This should be a count of documents hit for every type
        # in the search results.
        aggregations = search_results.pop('aggregations')
        concept_types = {
            bucket['key']: bucket['doc_count'] for bucket in
            aggregations['type-count']['buckets']
        }
        search_results.update({'total_items': total_items['count']})
        search_results.update({'concept_types': concept_types})
        return search_results

    async def search_variables(self, concept="", query="", size=None,
                               data_type=None, offset=0, fuzziness=1,
                               prefix_length=3, index=None):
        """
        In variable search, the concept MUST match one of the identifiers in the list
        The query can match search_terms (hence, "should") for ranking.

        Results Return
        The search result is returned in JSON format {collection_id:[elements]}

        Filter
        If a data_type is passed in, the result will be filtered to only contain
        the passed-in data type.
        """
        if self.is_simple_search_query(query):
            es_query = self.get_simple_variable_search_query(concept, query)
        else:
            es_query = self._get_var_query(concept, fuzziness, prefix_length, query)
        
        if index is None:
            index = "variables_index"

        total_items = await self.es.count(body=es_query, index=index)
        search_results = await self.es.search(
            index="variables_index",
            body=es_query,
            filter_path=['hits.hits._id', 'hits.hits._type',
                         'hits.hits._source', 'hits.hits._score'],
            from_=offset,
            size=size
        )

        search_result_hits = []

        if "hits" in search_results:
            search_result_hits = search_results['hits']['hits']

        return self._make_result(data_type, search_result_hits , total_items, True)

    async def search_vars_unscored(self, concept="", query="",
                                   size=None, data_type=None,
                                   offset=0, fuzziness=1,
                                   prefix_length=3):
        """
        In variable search, the concept MUST match one of the identifiers in the list
        The query can match search_terms (hence, "should") for ranking.

        Results Return
        The search result is returned in JSON format {collection_id:[elements]}

        Filter
        If a data_type is passed in, the result will be filtered to only contain
        the passed-in data type.
        """
        es_query = self._get_var_query(concept, fuzziness, prefix_length, query)
        total_items = await self.es.count(body=es_query, index="variables_index")
        search_results = []
        async for r in async_scan(self.es, query=es_query):
            search_results.append(r)

        return self._make_result(data_type, search_results, total_items, False)

    def _make_result(self, data_type, search_results, total_items, scored: bool):
        # Reformat Results
        new_results = {}
        if not search_results:
            # we don't want to error on a search not found
            new_results.update({'total_items': total_items['count']})
            return new_results
        for elem in search_results:
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
                "name": elem_s['element_name'],
                "metadata": elem_s.get('metadata', {})
            }

            if scored:
                elem_info["score"] = round(elem['_score'], 6)

            # Case: collection not in dictionary for given data_type
            if coll_id not in new_results[elem_type]:
                # initialize document
                doc = {
                    'c_id': coll_id,
                    'c_link': elem_s['collection_action'],
                    'c_name': elem_s['collection_name'],
                    'elements': [elem_info]
                }
                # save document
                new_results[elem_type][coll_id] = doc

            # Case: collection already in dictionary for given
            # element_type; append elem_info.  Assumes no duplicate
            # elements
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

        # better to update UI to accept optional "total_items" so it does not fail while fetching data for studies tab
        # and remove this if
        if not scored:
            new_results.update({'total_items': total_items['count']})

        return new_results

    async def search_kg(self, unique_id, query, offset=0, size=None,
                        fuzziness=1, prefix_length=3):
        """
        In knowledge graph search the concept MUST match the unique ID
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
        body = {'query': query}
        total_items = await self.es.count(body=body, index="kg_index")
        search_results = await self.es.search(
            index="kg_index",
            body=body,
            filter_path=['hits.hits._id', 'hits.hits._type',
                         'hits.hits._source'],
            from_=offset,
            size=size
        )
        search_results.update({'total_items': total_items['count']})
        return search_results

    async def search_study(self, study_id=None, study_name=None, offset=0, size=None):
        """
        Search for studies by unique_id (ID or name) and/or study_name.
        """
        # Define the base query
         # Define the base query
        query_body = {
            "bool": {
                "must": []
            }
        }
        
        # Add conditions based on user input
        if study_id:
            query_body["bool"]["must"].append({
                "match": {"collection_id": study_id}
            })
        
        if study_name:
            query_body["bool"]["must"].append({
                "match": {"collection_name": study_name}
            })

        print("query_body",query_body)
        body = {'query': query_body}
        total_items = await self.es.count(body=body, index="variables_index")
        search_results = await self.es.search(
            index="variables_index",
            body=body,
            filter_path=['hits.hits._id', 'hits.hits._type', 'hits.hits._source'],
            from_=offset,
            size=size
        )
        search_results.update({'total_items': total_items['count']})
        return search_results

    async def search_program(self, program_name=None, offset=0, size=None):
        """
        Search for studies by unique_id (ID or name) and/or study_name.
        """
 # Initialize the query_body with the outer structure
        query_body = {
            "query": {
                "bool": {
                    "must": []
                }
            },
            "aggs": {
                "unique_collection_ids": {
                    "terms": {
                        "field": "collection_id.keyword",
                        "size":1000
                    },
                    "aggs": {
                        "collection_details": {
                            "top_hits": {
                                "_source": ["collection_id", "collection_name", "collection_action"],
                                "size": 1
                            }
                        }
                    }
                }
            }
        }

        # Add conditions based on user input
        if program_name:
            # Lowercase the program_name before adding it to the query
            # program_name = program_name.lower()
            query_body["query"]["bool"]["must"].append(
                {"term": {"data_type.keyword": program_name}}
            )

        #print("query_body", query_body)

        # Prepare the query body for execution
        body = query_body
    
        # Execute the search query
        search_results = await self.es.search(
            index="variables_index",
            body=body,
            from_=offset,
            size=size
        )

        # The unique collection_ids and their details will be in the 'aggregations' field of the response
        unique_collection_ids = search_results['aggregations']['unique_collection_ids']['buckets']

        # Prepare a list to hold the collection details
        collection_details_list = []

        for bucket in unique_collection_ids:
            collection_details = bucket['collection_details']['hits']['hits'][0]['_source']
            # Append the details to the list in the desired format
            collection_details_list.append(collection_details)

    
            

       #Adding consent to the studies 
        with open(self._cfg.consent_id_path, 'r') as file:
            consent_id_mappings = json.load(file)
        # Add consent_id to the study
        updated_studies = []
        for study in collection_details_list:
            collection_id = study["collection_id"]
            if collection_id in consent_id_mappings:
                consent_ids = consent_id_mappings[collection_id]
                for consent_id in consent_ids:
                    updated_study = study.copy()
                    updated_study["collection_id"] = f"{collection_id}.{consent_id}"
                    updated_study["collection_action"] = f"{study['collection_action']}"
                    updated_studies.append(updated_study)
            else:
                updated_studies.append(study)
        


        #Adding missing studies
                
        with open(self._cfg.missing_studies_path, 'r') as file:
            missing_studies = json.load(file)
        for program in missing_studies:
            if program_name.lower() == program['program_name'].lower():
                updated_studies.extend(program['collections'])

                
        return updated_studies


    async def search_program_list(self):
        query_body = {
            "size": 0,  # We don't need the documents themselves, so set the size to 0
            "aggs": {
                "unique_program_names": {
                    "terms": {
                        "field": "data_type.keyword",
                        "size": 10000
                    },
                    "aggs": {
                        "No_of_studies": {
                            "cardinality": {
                                "field": "collection_id.keyword"
                            }
                        }
                    }
                }
            }
        }
        # Execute the search query
        search_results = await self.es.search(
            index="variables_index",
            body=query_body
        )
        # The unique data_types and their counts of unique collection_ids will be in the 'aggregations' field of the response
        unique_data_types = search_results['aggregations']['unique_program_names']['buckets']
        data=unique_data_types

        #Remove Parent program and add Training program
        
        data = [item for item in data if item['key'] != 'Parent']

        with open(self._cfg.missing_program_path, 'r') as file:
            missing_programs = json.load(file)
        data.extend(missing_programs)


        # Sorting the data alphabetically based on 'key'
        sorted_data = sorted(data, key=lambda x: (x['key'].casefold(), x['key'][1:]))

        #Add description as another field in exisiting data based on the program name
        descriptions_json = self._cfg.program_description
        descriptions = json.loads(descriptions_json)
        description_dict = {item['key']: {'description': item['description'], 'parent_program': item['parent_program']} for item in descriptions}

        # Add descriptions and parent programs to the sorted data
        for item in sorted_data:
            desc_info = description_dict.get(item['key'], {'description': '', 'parent_program': []})
            item['description'] = desc_info['description']
            item['parent_program'] = desc_info['parent_program']

        return sorted_data


    def _get_var_query(self, concept, fuzziness, prefix_length, query):
        """Returns ES query for variable search"""
        es_query = {
            "query": {
                'bool': {
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
        }
        if concept:
            es_query["query"]["bool"]["must"] = {
                "match": {
                    "identifiers": concept
                }
            }
        return es_query

    def get_simple_concept_search_query(self, query):
        """Returns ES query that allows to use basic operators like AND, OR, NOT...
        More info here https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-simple-query-string-query.html."""
        simple_query_string_search = {
            "query": query,
            "default_operator": "and",
            "flags": "OR|AND|NOT|PHRASE|PREFIX"
        }
        search_query = {
            "query": {
                "bool": {
                    "filter": {
                        "bool": {
                            "must": [
                                {"wildcard": {"description": "?*"}},
                                {"wildcard": {"name": "?*"}}
                            ]
                        }
                    },
                    "must": {
                        "function_score": {
                            "query": {
                                "bool": {
                                    "should": [
                                        {
                                            "simple_query_string": {
                                                **simple_query_string_search,
                                                "fields": ["name"]
                                            }
                                        },
                                        {
                                            "simple_query_string": {
                                                **simple_query_string_search,
                                                "fields": ["description"]
                                            }
                                        },
                                        {
                                            "simple_query_string": {
                                                **simple_query_string_search,
                                                "fields": ["search_terms"]
                                            }
                                        }
                                    ]
                                }
                            },
                            "score_mode": "sum"
                        }
                    }
                }
            }
        }
        return search_query

    def get_simple_variable_search_query(self, concept, query):
        """Returns ES query that allows to use basic operators like AND, OR, NOT...
        More info here https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-simple-query-string-query.html."""
        simple_query_string_search = {
            "query": query,
            "default_operator": "and",
            "flags": "OR|AND|NOT|PHRASE|PREFIX"
        }
        search_query = {
            "query": {
                "bool": {
                    "must": [
                        {"function_score": {
                            "query": {
                                "bool": {
                                    "should": [
                                        
                                        {
                                            "simple_query_string": {
                                                **simple_query_string_search,
                                                "fields": ["element_name"]
                                            }
                                        },
                                        {
                                            "simple_query_string": {
                                                **simple_query_string_search,
                                                "fields": ["element_desc"]
                                            }
                                        },
                                        {
                                            "simple_query_string": {
                                                **simple_query_string_search,
                                                "fields": ["search_terms"]
                                            }
                                        }
                                    ]
                                }
                            },
                            "score_mode": "sum"
                        }}
                    ]
                }
            }
        }
        if concept:
            search_query["query"]["bool"]["must"].append({
                "match": {
                    "identifiers": concept
                }
            })
        return search_query