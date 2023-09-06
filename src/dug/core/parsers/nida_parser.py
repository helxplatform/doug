import logging
import os
from typing import List
from xml.etree import ElementTree as ET

from dug import utils as utils
from ._base import DugElement, FileParser, Indexable, InputFile

logger = logging.getLogger('dug')


class NIDAParser(FileParser):
    # Class for parsers NIDA Data dictionary into a set of Dug Elements

    @staticmethod
    def parse_study_name_from_filename(filename: str):
        # Parse the study name from the xml filename if it exists. Return None if filename isn't right format to get id from
        stemname = os.path.splitext( os.path.basename(filename) )[0]
        if stemname.startswith("NIDA-"):
            sn = stemname
            for s in ["-Dictionary", "_DD"]:
                sn = sn.removesuffix(s) if sn.endswith(s) else sn
            return sn
        return None

    def __call__(self, input_file: InputFile) -> List[Indexable]:
        logger.debug(input_file)
        tree = ET.parse(input_file)
        root = tree.getroot()
        study_id = root.attrib['study_id']
        participant_set = root.get('participant_set','0')

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
            elem.collection_action = utils.get_nida_study_link(study_id=study_id)
            # Add to set of variables
            logger.debug(elem)
            elements.append(elem)

        # You don't actually create any concepts
        return elements
