import csv
import logging

from typing import List
import pandas as pd
from ._base import FileParser, InputFile, DugElement, DugConcept, Indexable
from dug.core.annotate import Normalizer, Identifier
from dug.config import Config as DugConfig
from dug.core.factory import DugFactory

logger = logging.getLogger('dug')


class PhenXParser(FileParser):
    PHENX_COL_NAME_NAME = 'PhenX Protocol'
    PHENX_COL_NAME_ID = 'PhenX ID'
    LOINC_COL_NAME_NAME = 'LOINC Name'
    LOINC_COL_NAME_ID = 'LOINC Code'
    CDE_COL_NAME_NAME = 'CDE Name'
    CDE_COL_NAME_ID = 'CDE Code'

    PHENX_CURIE_PREFIX = 'PhenX:'
    LOINC_CURIE_PREFIX = 'LOINC:'
    CDE_CURIE_PREFIX = 'CDE:'

    @staticmethod
    def get_parsed_row(file_name):
        read_file = pd.read_excel(file_name)
        df = pd.DataFrame(read_file)
        cols = df.columns
        # col_pairs = [(cols[i], cols[i + 1]) for i in range(0, len(cols) - 4, 2) if i < len(cols)]
        rows_all = []
        for row in df.iterrows():
            row_dict = {}
            for col_name in cols:  # , col_id in col_pairs:
                # col_to_curie_prefix_map = {'PhenX': 'PhenX', 'LOINC': 'LOINC', 'CDE': 'CDE'}
                if pd.notna(row[1][col_name]):
                    row_dict[col_name] = str(row[1][col_name]).strip()
            yield row_dict

    def __call__(self, input_file: InputFile)-> List[Indexable]:
        config = DugConfig.from_env()
        factory = DugFactory(config)
        http_session = factory.build_http_session()
        normalizer = Normalizer(**config.normalizer)
        logger.info(input_file)
        # Cde elements that just have cde code but no ontology ids from all rows
        cde_elements = []
        # Loinc elements from all rows
        loinc_elements = []
        # phenx elements from all rows
        phenx_elements = []
        # CDE cols from all rows  with ontology ids
        other_concepts = []

        # For each row
        for row in PhenXParser.get_parsed_row(input_file):
            # current phenx element
            phenx_element = None
            # current loinc element, note some rows have no loinc elements
            loinc_element = None

            # Create phenx Dug element from phenx Columns
            if PhenXParser.PHENX_COL_NAME_NAME in row and PhenXParser.PHENX_COL_NAME_ID in row:
                phenx_element = DugElement(
                    elem_id=row[PhenXParser.PHENX_COL_NAME_ID],
                    name=row[PhenXParser.PHENX_COL_NAME_NAME],
                    desc = row[PhenXParser.PHENX_COL_NAME_NAME],
                    elem_type='PhenX',
                    collection_id='',
                    collection_name=''
                )
                phenx_elements.append(phenx_element)

            # create loinc Dug element from loinc elements
            if PhenXParser.LOINC_COL_NAME_NAME in row and PhenXParser.LOINC_COL_NAME_ID in row:
                loinc_element = DugElement(
                    elem_id=row[PhenXParser.LOINC_COL_NAME_ID],
                    name=row[PhenXParser.LOINC_COL_NAME_NAME],
                    desc = row[PhenXParser.LOINC_COL_NAME_NAME],
                    elem_type='LOINC',
                    collection_id='',
                    collection_name=''
                )
                loinc_elements.append(loinc_element)

            # Start processing cde cols. When using the pandas parser multiple cols with same name are
            # indexed with an index suffix. Eg. CDE_Code, CDE_Code.1, CDE_Code.2 etc ... means xslx file
            # these cols.

            # Group dup Name and Id cols together
            cde_col_keys = [x for x in row.keys() if x.startswith('CDE')]
            name_cols = []
            id_cols = []
            for col in cde_col_keys:
                if PhenXParser.CDE_COL_NAME_NAME in col:
                    name_cols.append(col)
                if PhenXParser.CDE_COL_NAME_ID in col:
                    id_cols.append(col)
            current_cdes = []
            current_concepts = []

            # Sort and zip to loop in pairs of name and id col. EG (CDE_Name, CDE_Code), (CDE_Name.1, CDE_Code.1) ...
            for name, iD in zip(sorted(name_cols), sorted(id_cols)):
                is_ontology_id = False
                # Fix some cols that have typos
                if 'HP_' in row[iD]:
                    row[iD] = row[iD].replace('HP_', 'HP:')
                # Try to see if CDE Code is an ontology identifier.
                if ':' in row[iD]:
                    is_ontology_id = True

                # if not ontology id, treat as Dug element
                if not is_ontology_id:
                    cde_element = DugElement(
                        elem_id=row[iD],
                        name=row[name],
                        desc=row[name],
                        elem_type='CDE',
                        collection_id='',
                        collection_name=''
                    )
                    # ADD to current CDES since there are possibly more than one in a row.
                    # Keeping these for linking them to the current loinc and phenx elements.
                    current_cdes.append(cde_element)
                # If an ontological identifier
                # Normalize it and create a concept.
                else:
                    # Set default Biolink type to NamedThing
                    identifier = Identifier(id=row[iD], label=row[name], types=['biolink:NamedThing'])
                    # Call node norm service to get preferred
                    normalizer.normalize(identifier=identifier, http_session=http_session)
                    # Create a concept out of this
                    biolink_concept = DugConcept(
                        concept_id=identifier.id,
                        name=row[name],
                        desc='',
                        concept_type=identifier.types[0],
                    )
                    biolink_concept.add_identifier(identifier)
                    # add it to current rows concepts for linking
                    current_concepts.append(biolink_concept)
                    # add to the collection of all the concepts in the file
                    other_concepts.append(biolink_concept)

            # For each of the concepts in the current row
            for biolink_concept in current_concepts:
                # if we have a phenx element we add the normalized concept.
                # Similar to what happens in annotate step in dug.
                if phenx_element:
                    phenx_element.add_concept(biolink_concept)
                # Add concept to loinc
                if loinc_element:
                    loinc_element.add_concept(biolink_concept)


            # Link phenx with loinc
            # LOINC <-> PHENX
            if loinc_element and phenx_element:
                loinc_element.add_linked_element(phenx_element)
                phenx_element.add_linked_element(loinc_element)


            # Link CDES
            # CDE -> Phenx
            # CDE -> Loinc
            for cde in current_cdes:
                for concept in current_concepts:
                    cde.add_concept(concept)
                if loinc_element:
                    cde.add_linked_element(loinc_element)
                if phenx_element:
                    cde.add_linked_element(phenx_element)
                cde_elements.append(cde)
        return phenx_elements + loinc_elements + cde_elements + other_concepts
