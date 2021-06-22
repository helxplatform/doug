from dug.core.parsers import DbGaPParser, TOPMedTagParser, PhenXParser
from dug.core.parsers._base import DugElement, DugConcept
from tests.integration.conftest import TEST_DATA_DIR
from unittest.mock import patch
import requests


def test_db_gap_parser():
    parser = DbGaPParser()
    parse_file = str(TEST_DATA_DIR / "phs000166.v2.pht000700.v1.CAMP_CData.data_dict_2009_09_03.xml")
    elements = parser(parse_file)
    assert len(elements) > 0


def test_topmed_tag_parser():
    parser = TOPMedTagParser()
    parse_file = str(TEST_DATA_DIR / "test_variables_v2.0.csv")
    elements = parser(parse_file)
    assert len(elements) == 62
    for element in elements:
        assert element.name != element.id
        assert element.description != element.id


def test_phenx_parser():
    with patch('dug.core.factory.DugFactory.build_http_session', lambda *args, **kwargs : requests.session()):
        parser = PhenXParser()
        parser_file = str(TEST_DATA_DIR / "test_Protocol_cross_reference.xlsx")
        elements = parser(parser_file)
        assert len(elements) == 18
        #  Test counts
        count_of_bl_terms = 6
        bl_term_counter = 0
        phenx_el_count = 0
        loinc_el_count = 0
        cde_el_count = 0
        for x in elements:
            if isinstance(x, DugConcept):
                bl_term_counter += 1
            else:
                x : DugElement
                if x.type == 'PhenX':
                    phenx_el_count += 1
                if x.type == 'LOINC':
                    loinc_el_count += 1
                if x.type == 'CDE':
                    cde_el_count += 1
        assert bl_term_counter == count_of_bl_terms
        assert loinc_el_count == 4
        assert phenx_el_count == 4
        assert cde_el_count == 4
        # test linkage
        for element in elements:
            # Assert LOINC <-> phenx
            if element.id == '20501' and element.type == 'PhenX':
                # linked to the loinc on the same row
                assert len(element.linked_elements) == 1
                assert element.linked_elements[0].id == '62406-4'
                assert element.linked_elements[0].type == 'LOINC'
                # loinc in that row linked back?
                assert element.linked_elements[0].linked_elements[0] == element
                assert element.concepts.get('HP:0000240')
                assert element.linked_elements[0].concepts.get('HP:0000240')
            # test cde --> loinc and cde --> phenx
            if element.id == '2793421' and element.type == 'CDE':
                assert len(element.linked_elements) == 2
                linked_ids = [el.id for el in element.linked_elements]
                assert '20501' in linked_ids
                assert '62406-4' in linked_ids
                assert element.concepts.get('HP:0000240')