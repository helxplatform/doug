from dug.core.parsers._base import DugElement, DugConcept
from dug.core.annotators import DugIdentifier, AnnotateMonarch
# from dug.core.annotators.monarch_annotator import AnnotateMonarch


def test_dug_concept():
    concept = DugConcept("concept-1", 'Concept-1', 'The first concept', 'secondary')

    ident_1 = DugIdentifier("ident-1", "Identifier-1")
    ident_2 = DugIdentifier("ident-2", "Identifier-2")

    concept.add_identifier(ident_1)
    concept.add_identifier(ident_2)

    concept.clean()


def test_dug_concept_searchable_dict():

    concept_id = "concept-1"
    concept_name = 'Concept-1'
    concept_description = 'The first concept'
    concept_type = 'secondary'
    concept = DugConcept(
        concept_id,
        concept_name,
        concept_description,
        concept_type,
    )

    assert concept.get_searchable_dict() == {
        'id': concept_id,
        'name': concept_name,
        'description': concept_description,
        'type': concept_type,
        'search_terms': [],
        'optional_terms': [],
        'concept_action': "",
        'identifiers': [],
    }


def test_dug_element():
    elem_id = "1"
    elem_name = "Element-1"
    elem_desc = "The first element"
    elem_type = "primary"
    element = DugElement(
        elem_id, elem_name, elem_desc, elem_type, collection_id="", collection_name="", collection_desc=""
    )

    assert len(element.concepts) == 0
    element.add_concept(DugConcept("concept-1", 'Concept-1', 'The first concept', 'secondary'))
    assert len(element.concepts) == 1
    element.add_concept(DugConcept("concept-1", 'Concept-1', 'The first concept', 'secondary'))
    assert len(element.concepts) == 1


def test_dug_element_searchable_dict():
    elem_id = "1"
    elem_name = "Element-1"
    elem_desc = "The first element"
    elem_type = "primary"
    elem_collection_id = "C-1"
    elem_collection_name = "Collection 1"
    elem_collection_desc = "First collection"
    element = DugElement(
        elem_id, elem_name, elem_desc, elem_type,
        collection_id=elem_collection_id,
        collection_name=elem_collection_name,
        collection_desc=elem_collection_desc,
    )
    searchable = element.get_searchable_dict()
    assert searchable == {
        'element_id': elem_id,
        'element_name': elem_name,
        'element_desc': elem_desc,
        'collection_id': elem_collection_id,
        'collection_name': elem_collection_name,
        'collection_desc': elem_collection_desc,
        'element_action': "",
        'collection_action': "",
        'data_type': elem_type,
        "metadata": {},
        'identifiers': [],
        'search_terms': [],
        'optional_terms': []
    }

