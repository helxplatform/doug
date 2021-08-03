import pytest

from dug.utils import get_nida_study_link
import requests

@pytest.mark.skip("Implement this test")
def test_object_factory():
    pass


@pytest.mark.skip("Implement this test")
def test_complex_handler():
    pass


@pytest.mark.skip("Implement this test")
def test_get_dbgap_var_link():
    pass


@pytest.mark.skip("Implement this test")
def test_get_dbgap_study_link():
    pass


@pytest.mark.skip("Implement this test")
def test_parse_study_name_from_filename():
    pass

def test_get_nida_study_link():
    study_id = "NIDA-CPU-0008"
    link = get_nida_study_link(study_id=study_id)
    response = requests.post(
        url=link
    )
    content = str(response.text)
    assert content.count(study_id) > 0
    