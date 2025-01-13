import logging
from typing import List
from xml.etree import ElementTree as ET

from dug import utils as utils
from dug.core.parsers._base import DugElement, FileParser, Indexable, InputFile, DugConcept
import json


logger = logging.getLogger('dug')


class RADxParser(FileParser):

    def __call__(self, input_file: InputFile) -> List[Indexable]:
        with open(input_file) as stream:
            json_raw_data = json.load(stream)
        # get all records (records in radx json = variables)
        records = json_raw_data['records']
        elements = []
        for r in records:
            if r['studies']:
                concepts = r['terms'] or []
                concepts_objs = []
                for c in concepts:
                    concept_obj = DugConcept(
                        concept_id=c['identifier'],
                        name=c['label'],
                        concept_type="biolink:NamedThing",
                        desc="",
                    )
                    concept_obj.search_terms = c['synonyms']
                    concepts_objs.append(concept_obj)

                studies_dict = {x['id']: x for x in r['studies']}
                for s_id, s in studies_dict.items():
                    elem = DugElement(
                        elem_id=r['id'],
                        name=r['label'],
                        desc=r['description'],
                        elem_type=s['program'],
                        collection_id=s['phs'],
                        collection_name=s['study_name'],
                        collection_action=f"https://radxdatahub.nih.gov/study/{s['id']}"
                    )
                    for c in concepts_objs:
                        elem.add_concept(c)
                    elem.add_metadata(
                        {
                            'datatype': r['datatype'] or None,
                            'cardinality': r['cardinality'] or '',
                            'section': r['section'] or '',
                            'enumeration': r['enumeration'] or []
                         }
                    )
                    elements.append(elem)
        return elements
