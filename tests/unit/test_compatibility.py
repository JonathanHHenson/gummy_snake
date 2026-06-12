import pytest

import p5_py as p5
from p5_py import UnsupportedFeatureError


def test_dom_apis_are_explicitly_excluded():
    with pytest.raises(UnsupportedFeatureError):
        p5.createDiv("hello")


def test_table_and_xml_are_explicitly_excluded():
    with pytest.raises(UnsupportedFeatureError):
        p5.loadXML("data.xml")
    with pytest.raises(UnsupportedFeatureError):
        p5.loadTable("data.csv")
