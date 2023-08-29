import json
import logging
import sys

import requests
from elasticsearch import Elasticsearch

import redis
from redisgraph import Node, Edge, Graph, Path

from dug.core.annotate import Normalizer, Identifier, ConceptExpander

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

        # Establish the connection to RedisGraph
        print(f"Redis host is: {self._cfg.redis_host}")
        print(f"Redis port is: {self._cfg.redis_port}")
        print(f"Redis password is: {self._cfg.redis_password}")
        self.redisConn = redis.Redis(host=self._cfg.redis_host, port=self._cfg.redis_port, password=self._cfg.redis_password)
        #print(f"Connecting to graph: {self._cfg.redis_graph}")
        self.redisGraph = Graph(self._cfg.redis_graph, self.redisConn)
        #print(f"graph connection: {self.redisGraph}")

        # At this point, we would like to test the connnection, but there does not seem to be a command
        # to do so.  We could probably execute a No-op type command.

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
                "number_of_replicas": 0,
                "analysis": {
                   "analyzer": {
                     "std_with_stopwords": { 
                       "type":      "standard",
                       "stopwords": "_english_"
                     }
                  }
               }
            },
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "id": {"type": "text", "analyzer": "std_with_stopwords", "fields": {"keyword": {"type": "keyword"}}},
                    "name": {"type": "text", "analyzer": "std_with_stopwords"},
                    "description": {"type": "text", "analyzer": "std_with_stopwords"},
                    "type": {"type": "keyword"},
                    "search_terms": {"type": "text", "analyzer": "std_with_stopwords"},
                    "identifiers": {
                        "properties": {
                            "id": {"type": "text", "analyzer": "std_with_stopwords", "fields": {"keyword": {"type": "keyword"}}},
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
                "number_of_replicas": 0,
                "analysis": {
                   "analyzer": {
                     "std_with_stopwords": { 
                       "type":      "standard",
                       "stopwords": "_english_"
                     }
                  }
               }
            },
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "element_id": {"type": "text", "analyzer": "std_with_stopwords", "fields": {"keyword": {"type": "keyword"}}},
                    "element_name": {"type": "text", "analyzer": "std_with_stopwords"},
                    "element_desc": {"type": "text", "analyzer": "std_with_stopwords"},
                    "element_action": {"type": "text", "analyzer": "std_with_stopwords"},
                    "search_terms": {"type": "text", "analyzer": "std_with_stopwords"},
                    "optional_terms": {"type": "text", "analyzer": "std_with_stopwords"},
                    "identifiers": {"type": "keyword"},
                    "collection_id": {"type": "text", "analyzer": "std_with_stopwords", "fields": {"keyword": {"type": "keyword"}}},
                    "collection_name": {"type": "text", "analyzer": "std_with_stopwords"},
                    "collection_desc": {"type": "text", "analyzer": "std_with_stopwords"},
                    "collection_action": {"type": "text", "analyzer": "std_with_stopwords"},
                    "data_type": {"type": "text", "analyzer": "std_with_stopwords", "fields": {"keyword": {"type": "keyword"}}}
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

    def dump_concepts(self, index, query={}, offset=0, size=None, fuzziness=1, prefix_length=3):
        """
        Get everything from concept index
        """
        query = {
            "match_all" : {}
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

    def query_description(self, concept):
       # This call dummied up for now in the hope that it can eventually be removed
       return({'dummy':'response'})
       # Currently the description for the concept is not reliably in the graph.
       # so we are retrieving it from a hard coded URL.  This is OK because we expect
       # to move the descriptions into the RedisGraph and this code will go away.
       url = f"https://api.monarchinitiative.org/api/bioentity/{concept}"
       #print("***********************************************************")
       #print(f"retrieving URL: {url}")
       response = requests.get(url)
       #print(json.dumps(response.json(),indent=4))
       #print("***********************************************************")
       return(response.json())

    def query_redis(self, concept, leafType, queryList):
        # Variable/study queries
        # Get the CDEs
        #queryList.append("""MATCH (c{id:"CONCEPT"})-->(b:`biolink:Publication`) return c,b""")
        #queryList.append("""MATCH(c:`TYPE`{id:"CONCEPT"})-->(b:biolink:StudyVariable)-->(d:biolink:Study) return b,d""")
        #print (queryList[0])

        allResults = None
        # send each query to the lower level for query execution and data extraction
        for query in queryList:
           theseResults = self.execute_redis_query(concept, leafType, query)
           print(f"nResults of query is {len(theseResults)}")
           if allResults is None:
              allResults = theseResults
           else:
              allResults = allResults + theseResults

        return allResults   

    def execute_redis_query(self, concept, leafType, protoQuery): 
        #print(f"concept is {concept}")
        #print(f"leafType is {leafType}")
        query1 = protoQuery.replace("CONCEPT", concept)
        leafType = leafType.replace("biolink:", '')
        query1 = query1.replace("TYPE", leafType)
        print(f"query to execute is {query1}")

        results1 = self.redisGraph.query(query1)
        #print(f"results1 is {results1}")
        #print(type(results1.result_set))
        #print(len(results1.result_set))
        #resultNum = 0
        #for record in results1.result_set:
           #print(len(record))
           #print(f"************************** Record 0 Result {resultNum} *********************************")
           #print(type(record[0]))
           #string1 = record[0].toString()
           #print(f"theRecord: {string1}")
           #print("***********************************************************")
           #print(json.dumps(record[0].properties, indent=4))
           #print(f"************************** Record 1 Result {resultNum} *********************************")
           #print(json.dumps(record[1].properties, indent=4))
           #print(f"************************** Record 2 Result {resultNum} *********************************")
           #print(json.dumps(record[2].properties, indent=4))
           #resultNum = resultNum + 1

        return results1.result_set

    def normalize_query(self, query):
        params = {'text': query, 'model_name': self._cfg.ner_model}
        response = requests.post(self._cfg.ner_url, json=params)
        print(self._cfg.ner_url)
        print(response)
        print(response.json())
        theJSON = response.json()
        theMeshTerm = 'MESH:' + theJSON[0]['curie']
        print(f"theMeshTerm is {theMeshTerm}")

        # We want to normalize the term to the most preferred entry so that
        # when we query the graph we get the best results.
        normalizer = Normalizer(**self._cfg.normalizer)
        identifier = Identifier(theMeshTerm, theJSON[0])
        normalizedResult = None
        with requests.session() as session:
          normalizedResult = normalizer.normalize(identifier, session)
          print(f"identifier: {identifier}")
          print(f"normalized result: {normalizedResult.types[0]}")
        return normalizedResult

    def search_concepts(self, index, query, offset=0, size=None, fuzziness=1, prefix_length=3):

        # Which query set we want to run is defined by the env var QUERY_SET. QUERY_SET must be
        # one of "One", "Two, "Left", "Right". If none of these is found, it's an error
        print(self._cfg.query_set)
        query_set = self._cfg.query_set
        # Let's query the NER endpoint for the user query
        normalizedResult = self.normalize_query(query)
        leafType = normalizedResult.types[0]
        description = self.query_description(normalizedResult.id)
        #print(f"description: {description}")

        queryList = []
        # Concept queries
        # Does the user provided concept have any variables. 
        if (query_set == "One"):
           # The following 3 queries used for "one hop"
           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) return c""")

           # Find concepts one hop away from the user concept that have variables
           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})--(x)--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) where labels(x) <> "biolink:StudyVariable" return distinct x""")
     
           # Find concepts one hop away that are related to CDE
           queryList.append("""MATCH (c{id:"CONCEPT"})--(x)--(b:`biolink:Publication`) return distinct x""")
           #################################################################################################
           
        elif (query_set == "Two"):
           # The following 2 queries used for "two hop"
           # Find concepts 2 hops away from the user concept that have variables restricted by subclass
           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})--(y)--(x)--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) where labels(x) <> "biolink:StudyVariable" return distinct x""")

           # Find concepts two hops away that are related to CDE
           queryList.append("""MATCH (c{id:"CONCEPT"})--(y)--(x)--(b:`biolink:Publication`) return distinct x""")
           #################################################################################################
           
        elif (query_set == "Two-New"):
           # The following 2 queries used for "two hop"
           # Find concepts 2 hops away from the user concept that have variables restricted by subclass
           #queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})-[a]-(y)-[e]-(x)--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) where labels(x) <> "biolink:StudyVariable"  return distinct x""")

           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})-[a]-(y)-[e]-(x)--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) where labels(x) <> "biolink:StudyVariable" and not (type(a) = "biolink:subclass_of" and type(e) = "biolink:subclass_of" and startnode(a) = c and startnode(e) = x) return distinct x""")

           # Find concepts two hops away that are related to CDE
           #queryList.append("""MATCH (c{id:"CONCEPT"})--(y)--(x)--(b:`biolink:Publication`) return distinct x""")
           #################################################################################################

        elif (query_set == "Right-old"):
           # The following queries used for "right subclass"
           # Find concepts 2 hops away from the user concept that have variables
           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})--(y)<-[e:`biolink:subclass_of`]-(x)--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) where labels(x) <> "biolink:StudyVariable" return distinct x""")
           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})--(y)<-[e:`biolink:subclass_of`]-(x)--(b:`biolink:Publication`) return distinct x""")
           #################################################################################################


        elif (query_set == "Right"):
           # The following queries used for "right subclass"
           # Find concepts 2 hops away from the user concept that have variables
           #queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})-[g]-(y)<-[e:`biolink:subclass_of`]-(x)--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) where labels(x) <> "biolink:StudyVariable" and where type(g) <> `biolink:subclass_of` and not c pointing to y return distinct x""")
           #queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})-[g]-(y)<-[e:`biolink:subclass_of`]-(x)--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) where labels(x) <> "biolink:StudyVariable" return distinct x""")
           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})-[g]-(y)<-[e:`biolink:subclass_of`]-(x)--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) where labels(x) <> "biolink:StudyVariable" and not (endnode(g) = endnode(e) and type(g) = "biolink:subclass_of") return distinct x""")
           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})-[g]-(y)<-[e:`biolink:subclass_of`]-(x)--(b:`biolink:Publication`) where not (endnode(g) = endnode(e) and type(g) = "biolink:subclass_of") return distinct x""")
           #################################################################################################



        elif (query_set == "Left"):
           # The following query used for "left subclass"
           # 11/20/2022 CAB suggestion
           # Find concepts 2 hops away from the user concept that have variables restricted by subclass
           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})<-[e:`biolink:subclass_of`]-(y)--(x)--(b:`biolink:StudyVariable`)--(d:`biolink:Study`) where labels(x) <> "biolink:StudyVariable" return distinct x""")
           queryList.append("""MATCH(c:`biolink:TYPE`{id:"CONCEPT"})<-[e:`biolink:subclass_of`]-(y)--(x)--(b:`biolink:Publication`) return distinct x""")
           #################################################################################################
        else:
           print("No valid query set selected. Set the QUERY_SET env var to One, Two, Left or Right")
           sys.exit(0)
        graphResults = self.query_redis(normalizedResult.id, leafType, queryList)  
        #print(f"number of graphResults is {len(graphResults)}")

        # Build the result object.  This is going to match what was returned from the ElasticSearch search
        redisResults = {}
        redisResults['query_list'] = queryList
        redisResults['query_set'] = query_set
        redisResults['status'] = 'success'
        redisResults['query'] = query
        redisResults['concept'] = normalizedResult.id
        redisResults['result'] = {}
        redisResults['result']['hits'] = {}
        redisResults['result']['hits']['hits'] = []
        
        # for each result in the graph results, we build json that matches the used parts of
        # the existing ElasticSearch json and 
        # add it to the redisResults['results']['hits']['hits'] array
        node = 0
        for thisRecord in graphResults:
           thisJson = {}
           thisJson['_type'] = '_doc'
           thisJson['_id'] = thisRecord[node].properties['id']
           description = self.query_description(thisRecord[node].properties['id'])
           #print(f"description: {json.dumps(description, indent=4)}")
           resultSource = {}
           resultSource['_id'] = thisRecord[node].properties['id']
           #resultSource['name'] = description.get('label', thisRecord[node].properties['name'])
           if 'name' in thisRecord[node].properties:
              resultSource['name'] = thisRecord[node].properties['name']
           else:
              resultSource['name'] = 'None'
           #print('*************************************************')
           #print(resultSource['_id'])
           #print(resultSource['name'])

           # The below code is commented out because, for development purposes, we are going to
           # avoid calling the monarch API for now. In the long run, we should probably add whatever
           # info we get from that code to the redis graph so that the API call is unneeded at
           # query time.
           #if 'error' in description.keys():
           #   resultSource['type'] = ""
           #elif  description['category'] is None:
           #   resultSource['type'] = ""
           #else:
           #   resultSource['type'] = description['category'][0]
           thisJson['_source'] = resultSource
           redisResults['result']['hits']['hits'].append(thisJson)
        
        #print(json.dumps(redisResults, indent = 4))
        redisResults['result']['total_items'] = len(graphResults)
        redisResults['message'] = 'Search result'
        #print(json.dumps(redisResults, indent=4))
        return redisResults

        #search_results.update({'total_items': total_items['count']})
        #return search_results

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
        # Variable/study queries
        # Get the CDEs
        # Let's query the NER endpoint for the user query
        normalizedResult = self.normalize_query(query)
        leafType = normalizedResult.types[0]
        description = self.query_description(normalizedResult.id)
        queryList = []
        queryList.append("""MATCH (c{id:"CONCEPT"})-->(b:`biolink:Publication`) return c,b""")
        queryList.append("""MATCH(c:`TYPE`{id:"CONCEPT"})-->(b:`biolink:StudyVariable`) return c,b""")
        #queryList.append("""MATCH(c:`TYPE`{id:"CONCEPT"})-->(b:`biolink:StudyVariable`)-->(d:`biolink:Study`) return b,d""")
        #print (queryList[0])
        graphResults = self.query_redis(normalizedResult.id, leafType, queryList)  
        print(f"number of graphResults is {len(graphResults)}")
        for thisRecord in graphResults:
           print("***********************************************************")
           print(f"properties c: {thisRecord[0].properties}")
           print("***********************************************************")
           print(f"properties b: {thisRecord[1].properties}")
           thisJson = {}
           #thisJson['_type'] = '_doc'
           #thisJson['_id'] = thisRecord[node].properties['id']

        return
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
        total_items = self.es.count(body=body, index=index)
        search_results = self.es.search(
            index=index,
            body=body,
            filter_path=['hits.hits._id', 'hits.hits._type', 'hits.hits._source', 'hits.hits._score'],
            from_=offset,
            size=size
        )

        # Reformat Results
        new_results = {}
        if not search_results:
           # we don't want to error on a search not found
           new_results.update({'total_items': total_items['count']})
           return new_results

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
                "name": elem_s['element_name'],
                "score": round(elem['_score'], 6)
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
