import logging
from typing import Dict

import pluggy

from ._base import DugElement, DugConcept, Indexable, Parser, FileParser
from .dbgap_parser import DbGaPParser
from .nida_parser import NIDAParser
from .scicrunch_parser import SciCrunchParser
from .topmed_tag_parser import TOPMedTagParser
from .topmed_csv_parser import TOPMedCSVParser
from .anvil_dbgap_parser import AnvilDbGaPParser

logger = logging.getLogger('dug')

hookimpl = pluggy.HookimplMarker("dug")


@hookimpl
def define_parsers(parser_dict: Dict[str, Parser]):
    parser_dict["dbgap"] = DbGaPParser()
    parser_dict["nida"] = NIDAParser()
    parser_dict["topmedtag"] = TOPMedTagParser()
    parser_dict["topmedcsv"] = TOPMedCSVParser()
    parser_dict["scicrunch"] = SciCrunchParser()
    parser_dict["anvil"] = AnvilDbGaPParser() 


class ParserNotFoundException(Exception):
    ...


def get_parser(hook, parser_name) -> Parser:
    """Get the parser from all parsers registered via the define_parsers hook"""

    available_parsers = {}
    hook.define_parsers(parser_dict=available_parsers)
    parser = available_parsers.get(parser_name.lower())
    if parser is not None:
        return parser

    err_msg = f"Cannot find parser of type '{parser_name}'\n" \
              f"Supported parsers: {', '.join(available_parsers.keys())}"
    logger.error(err_msg)
    raise ParserNotFoundException(err_msg)
