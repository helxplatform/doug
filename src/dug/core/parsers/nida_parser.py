import logging
import re
from typing import List
from xml.etree import ElementTree as ET

from dug import utils as utils
from ._base import DugElement, FileParser, Indexable, InputFile

logger = logging.getLogger('dug')


class NidaParser(FileParser):
    # Class for parsers NIDA Data dictionary into a set of Dug Elements

    @staticmethod
    def parse_study_name_from_filename(filename: str):
        # Parse the study name from the xml filename if it exists. Return None if filename isn't right format to get id from
        nida_file_pattern = re.compile(r'.*/*phs[0-9]+\.v[0-9]\.pht[0-9]+\.v[0-9]\.(.+)\.data_dict.*')
        match = re.match(nida_file_pattern, filename)
        if match is not None:
            return match.group(1)
        return None

    def __call__(self, input_file: InputFile) -> List[Indexable]:
        logger.debug(input_file)
        tree = ET.parse(input_file)
        root = tree.getroot()
        study_id = root.attrib['study_id']
        participant_set = root.attrib['participant_set']

        # Parse study name from file handle
        study_name = self.parse_study_name_from_filename(str(input_file))

        if study_name is None:
            err_msg = f"Unable to parse NIDA study name from data dictionary: {input_file}!"
            logger.error(err_msg)
            raise IOError(err_msg)

        elements = []
        for variable in root.iter('variable'):
            elem = DugElement(elem_id=f"{variable.attrib['id']}.p{participant_set}",
                              name=variable.find('name').text,
                              desc=variable.find('description').text.lower(),
                              elem_type="NIDA",
                              collection_id=f"{study_id}.p{participant_set}",
                              collection_name=study_name)

            # Create NIDA links as study/variable actions
            elem.collection_action = utils.get_dbgap_study_link(study_id=elem.collection_id)
            elem.action = utils.get_dbgap_var_link(study_id=elem.collection_id,
                                                   variable_id=elem.id.split(".")[0].split("phv")[1])
            # Add to set of variables
            logger.debug(elem)
            elements.append(elem)

        # You don't actually create any concepts
        return elements
