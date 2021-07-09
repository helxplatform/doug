import json
import logging
import os
import traceback

from dug.core.parsers import Parser, DugElement, DugConcept

logger = logging.getLogger('dug')


class Crawler:
    def __init__(self, crawl_file: str, parser: Parser, annotator,
                 tranqlizer, tranql_queries,
                 http_session, exclude_identifiers=None, element_type=None):

        if exclude_identifiers is None:
            exclude_identifiers = []

        self.crawl_file = crawl_file
        self.parser: Parser = parser
        self.element_type = element_type
        self.annotator = annotator
        self.tranqlizer = tranqlizer
        self.tranql_queries = tranql_queries
        self.http_session = http_session
        self.exclude_identifiers = exclude_identifiers
        self.elements = []
        self.concepts = {}
        self.crawlspace = "crawl"

    def make_crawlspace(self):
        if not os.path.exists(self.crawlspace):
            try:
                os.makedirs(self.crawlspace)
            except Exception as e:
                print(f"-----------> {e}")
                traceback.print_exc()

    def crawl(self):

        # Create directory for storing temporary results
        self.make_crawlspace()

        # Read in elements from parser
        self.elements = self.parser(self.crawl_file)

        # Optionally coerce all elements to be a specific type
        for element in self.elements:
            if isinstance(element, DugElement) and self.element_type is not None:
                element.type = self.element_type

        # Annotate elements
        self.annotate_elements()

        # Expand concepts
        concept_file = open(f"{self.crawlspace}/concept_file.json", "w")
        for concept_id, concept in self.concepts.items():
            # Use TranQL queries to fetch knowledge graphs containing related but not synonymous biological terms
            self.expand_concept(concept)

            # Traverse identifiers to create single list of of search targets/synonyms for concept
            concept.set_search_terms()

            # Traverse kg answers to create list of optional search targets containing related concepts
            concept.set_optional_terms()

            # Remove duplicate search terms and optional search terms
            concept.clean()

            # Write concept out to a file
            concept_file.write(f"{json.dumps(concept.get_searchable_dict(), indent=2)}")

        # Set element optional terms now that concepts have been expanded
        # Open variable file for writing
        variable_file = open(f"{self.crawlspace}/element_file.json", "w")
        for element in self.elements:
            if isinstance(element, DugElement):
                element.set_optional_terms()
                variable_file.write(f"{element.get_searchable_dict()}\n")

        # Close concept, element files
        concept_file.close()
        variable_file.close()

    def annotate_elements(self):

        logger.info(f"len(elements): {len(self.elements)}")
        # Annotate elements/concepts and create new concepts based on the ontology identifiers returned
        #for element in self.elements:
        for n, element in enumerate(self.elements):
            # If element is actually a pre-loaded concept (e.g. TOPMed Tag), add that to list of concepts
            if isinstance(element, DugConcept):
                self.concepts[element.id] = element

            # Annotate element with normalized ontology identifiers
            self.annotate_element(element, n, len(self.elements))
            if isinstance(element, DugElement):
                element.set_search_terms()

        # Now that we have our concepts and elements fully annotated, we need to
        # Make sure elements inherit the identifiers from their user-defined parent concepts
        # E.g. TOPMedTag1 was annotated with HP:123 and MONDO:12.
        # Each element assigned to TOPMedTag1 needs to be associated with those concepts as well
        for element in self.elements:
            # Skip user-defined concepts
            if isinstance(element, DugConcept):
                continue

            # Associate identifiers from user-defined concepts (see example above)
            # with child elements of those concepts
            concepts_to_add = []
            for concept_id, concept in element.concepts.items():
                for ident_id, identifier in concept.identifiers.items():
                    if ident_id not in element.concepts and ident_id in self.concepts:
                        concepts_to_add.append(self.concepts[ident_id])

            for concept_to_add in concepts_to_add:
                element.add_concept(concept_to_add)

    def annotate_element(self, element, n, ntot):

        logger.info(f"annotate_element #{n}/{ntot}")

        # Annotate with a set of normalized ontology identifiers
        identifiers = self.annotator.annotate(text=element.ml_ready_desc,
                                              http_session=self.http_session)

        # Each identifier then becomes a concept that links elements together
        for identifier in identifiers:
            if identifier.id not in self.concepts:
                # Create concept for newly seen identifier
                concept = DugConcept(concept_id=identifier.id,
                                                       name=identifier.label,
                                                       desc=identifier.description,
                                                       concept_type=identifier.type)
                # Add to list of concepts
                self.concepts[identifier.id] = concept

            # Add identifier to list of identifiers associated with concept
            self.concepts[identifier.id].add_identifier(identifier)

            # Create association between newly created concept and element
            # (unless element is actually a user-defined concept)
            if isinstance(element, DugElement):
                element.add_concept(self.concepts[identifier.id])

            # If element is actually a user defined concept (e.g. TOPMedTag), associate ident with concept
            # Child elements of these user-defined concepts will inherit all these identifiers as well.
            elif isinstance(element, DugConcept):
                element.add_identifier(identifier)

    def expand_concept(self, concept):

        # Get knowledge graphs of terms related to each identifier
        for ident_id, identifier in concept.identifiers.items():

            # Conditionally skip some identifiers if they are listed in config
            if ident_id in self.exclude_identifiers:
                continue

            # Use pre-defined queries to search for related knowledge graphs that include the identifier
            for query_name, query_factory in self.tranql_queries.items():

                # Skip query if the identifier is not a valid query for the query class
                if not query_factory.is_valid_curie(ident_id):
                    logger.info(f"identifier {ident_id} is not valid for query type {query_name}. Skipping!")
                    continue

                # Fetch kg and answer
                kg_outfile = f"{self.crawlspace}/{ident_id}_{query_name}.json"
                answers = self.tranqlizer.expand_identifier(ident_id, query_factory, kg_outfile)

                # Add any answer knowledge graphs to
                for answer in answers:
                    concept.add_kg_answer(answer, query_name=query_name)
