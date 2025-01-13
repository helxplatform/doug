import json
from typing import Union, Callable, Any, Iterable

from dug.core.loaders import InputFile

from dug import utils as utils


class DugElement:
    # Basic class for holding information for an object you want to make searchable via Dug
    # Could be a DbGaP variable, DICOM image, App, or really anything
    # Optionally can hold information pertaining to a containing collection (e.g. dbgap study or dicom image series)
    def __init__(self, elem_id, name, desc, elem_type, collection_id="", collection_name="", collection_desc="", action="", collection_action=""):
        self.id = elem_id
        self.name = name
        self.description = desc
        self.type = elem_type
        self.collection_id = collection_id
        self.collection_name = collection_name
        self.collection_desc = collection_desc
        self.action = action
        self.collection_action = collection_action
        self.concepts = {}
        self.ml_ready_desc = desc
        self.search_terms = []
        self.optional_terms = []
        self.metadata = {}



    def add_concept(self, concept):
        self.concepts[concept.id] = concept

    def jsonable(self):
        """Output a pickleable object"""
        return self.__dict__

    def get_searchable_dict(self):
        # Translate DugElement to ES-style dict
        es_elem = {
            'element_id': self.id,
            'element_name': self.name,
            'element_desc': self.description,
            'search_terms': self.search_terms,
            'optional_terms': self.optional_terms,
            'collection_id': self.collection_id,
            'collection_name': self.collection_name,
            'collection_desc': self.collection_desc,
            'element_action': self.action,
            'collection_action': self.collection_action,
            'data_type': self.type,
            'metadata': self.metadata,
            'identifiers': list(self.concepts.keys())
        }
        return es_elem

    def add_metadata(self, metadata):
        self.metadata = metadata

    def get_id(self):
        return f'{self.id}-{self.collection_id}'

    def set_search_terms(self):
        search_terms = []
        for concept_id, concept in self.concepts.items():
            concept.set_search_terms()
            search_terms.extend(concept.search_terms)
            search_terms.append(concept.name)
        search_terms = sorted(list(set(search_terms)))
        self.search_terms = search_terms

    def set_optional_terms(self):
        optional_terms = []
        for concept_id, concept in self.concepts.items():
            concept.set_optional_terms()
            optional_terms.extend(concept.optional_terms)
        optional_terms = sorted(list(set(optional_terms)))
        self.optional_terms = optional_terms

    def __str__(self):
        return json.dumps(self.__dict__, indent=2, default=utils.complex_handler)


class DugConcept:
    # Basic class for holding information about concepts that are used to organize elements
    # All Concepts map to at least one element
    def __init__(self, concept_id, name, desc, concept_type):
        self.id = concept_id
        self.name = name
        self.description = desc
        self.type = concept_type
        self.concept_action = ""
        self.identifiers = {}
        self.kg_answers = {}
        self.search_terms = []
        self.optional_terms = []
        self.ml_ready_desc = desc

    def add_identifier(self, ident):
        if ident.id in self.identifiers:
            for search_text in ident.search_text:
                self.identifiers[ident.id].add_search_text(search_text)
        else:
            self.identifiers[ident.id] = ident

    def add_kg_answer(self, answer, query_name):
        answer_node_ids = list(answer.nodes.keys())
        answer_id = f'{"_".join(answer_node_ids)}_{query_name}'
        if answer_id not in self.kg_answers:
            self.kg_answers[answer_id] = answer

    def clean(self):
        self.search_terms = sorted(list(set(self.search_terms)))
        self.optional_terms = sorted(list(set(self.optional_terms)))

    def set_search_terms(self):
        # Traverse set of identifiers to determine set of search terms
        search_terms = self.search_terms
        for ident_id, ident in self.identifiers.items():
            search_terms.extend(ident.search_text + ident.synonyms)
        self.search_terms = sorted(list(set(search_terms)))

    def set_optional_terms(self):
        # Traverse set of knowledge graph answers to determine set of optional search terms
        optional_terms = self.optional_terms
        for kg_id, kg_answer in self.kg_answers.items():
            optional_terms += kg_answer.get_node_names()
            optional_terms += kg_answer.get_node_synonyms()
        self.optional_terms = sorted(list(set(optional_terms)))

    def get_searchable_dict(self):
        # Translate DugConcept into Elastic-Compatible Concept
        es_conc = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'type': self.type,
            'search_terms': self.search_terms,
            'optional_terms': self.optional_terms,
            'concept_action': self.concept_action,
            'identifiers': [ident.get_searchable_dict() for ident_id, ident in self.identifiers.items()]
        }
        return es_conc

    def jsonable(self):
        """Output a pickleable object"""
        return self.__dict__

    def __str__(self):
        return json.dumps(self.__dict__, indent=2, default=utils.complex_handler)


Indexable = Union[DugElement, DugConcept]
Parser = Callable[[Any], Iterable[Indexable]]


FileParser = Callable[[InputFile], Iterable[Indexable]]