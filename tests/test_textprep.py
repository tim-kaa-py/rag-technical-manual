"""Tests use verbatim line shapes found in the Teksan manual (see D9 analysis)."""

from src.textprep import clean_page_text, detect_heading


def test_clean_removes_header_and_footer_lines():
    raw = (
        "EVERLASTING COMPANY\n"
        "5.6. Fuel\n"
        "Use fuel conforming to EN590.\n"
        "BBK-V.122018_ENG 43 People First\n"
    )
    cleaned = clean_page_text(raw)
    assert "EVERLASTING" not in cleaned
    assert "BBK-V.122018_ENG" not in cleaned
    assert "People First" not in cleaned
    assert "Use fuel conforming to EN590." in cleaned
    assert "5.6. Fuel" in cleaned  # headings survive cleaning


def test_clean_removes_multiline_logo_as_pypdf_extracts_it():
    # pypdf renders the page logo as four standalone lines, twice per page
    raw = (
        "EVERLASTING\n"
        "WE\n"
        "COMPANY\n"
        "AREYOUR\n"
        "EVERLASTING\n"
        "WE\n"
        "COMPANY\n"
        "AREYOUR\n"
        "5.4.Lubrication Oil\n"
        "The lubrication oil must be changed periodically.\n"
    )
    cleaned = clean_page_text(raw)
    for logo_word in ("EVERLASTING", "AREYOUR"):
        assert logo_word not in cleaned
    assert "WE\n" not in cleaned and not cleaned.startswith("WE")
    assert "The lubrication oil must be changed periodically." in cleaned
    assert "5.4.Lubrication Oil" in cleaned


def test_detect_heading_matches_all_four_manual_formats():
    # dot-glued, dot-space, hyphen, space (the four formats Ingrid found)
    assert detect_heading("1.SAFETY PRECAUTIONS") == "1 SAFETY PRECAUTIONS"
    assert detect_heading("2. GENERAL DEFINITIONS") == "2 GENERAL DEFINITIONS"
    assert detect_heading("3-INSTALLATION") == "3 INSTALLATION"
    assert detect_heading("2.2.1 Canopy Type") == "2.2.1 Canopy Type"
    assert detect_heading("1.2.1.Using Slings") == "1.2.1 Using Slings"
    assert detect_heading("5.11. General Maintenance Schedule") == (
        "5.11 General Maintenance Schedule"
    )


def test_clean_drops_leading_page_number_line():
    # the printed page number extracts as the first line of every page; left in,
    # it defeats heading-at-chunk-start detection (section labels shift by one)
    raw = "42\n\n5.4.Lubrication Oil\nOil text."
    cleaned = clean_page_text(raw)
    assert not cleaned.startswith("42")
    assert "5.4.Lubrication Oil" in cleaned


def test_detect_heading_rejects_false_positives():
    assert detect_heading("Use fuel conforming to EN590.") is None  # prose
    assert detect_heading("0,5 - 1,0") is None  # table row (comma)
    assert detect_heading("20 Ohms maximum grounding resistance") is None  # digit + unit
    assert detect_heading("10 Fuel Feed Pump") is None  # diagram legend item (p. 29)
    assert detect_heading("") is None
