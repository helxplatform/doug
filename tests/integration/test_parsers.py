from dug.core.parsers import DbGaPParser, TOPMedTagParser
from tests.integration.conftest import TEST_DATA_DIR


def test_db_gap_parser():
    parser = DbGaPParser()
    parse_file = str(TEST_DATA_DIR / "phs000166.v2.pht000700.v1.CAMP_CData.data_dict_2009_09_03.xml")
    elements = parser(parse_file)
    assert len(elements) > 0
    parse_file = str(TEST_DATA_DIR / "NIDA-CPU0008-Dictionary.xml")
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
