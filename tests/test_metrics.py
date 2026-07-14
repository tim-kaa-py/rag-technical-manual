from eval.metrics import hit, pages_found, reciprocal_rank


def test_hit_when_any_retrieved_chunk_page_is_expected():
    assert hit(["10", "43", "12", "43", "9"], {"43"}) is True
    assert hit(["10", "11", "12", "13", "14"], {"43"}) is False


def test_reciprocal_rank_uses_first_matching_chunk_position():
    # chunks, not pages, define rank (D17); rank is 1-based
    assert reciprocal_rank(["10", "43", "12", "43", "9"], {"43"}) == 0.5
    assert reciprocal_rank(["43", "10", "11", "12", "13"], {"43"}) == 1.0
    assert reciprocal_rank(["10", "11", "12", "13", "14"], {"43"}) == 0.0  # RR=0 on miss


def test_pages_found_reports_multi_page_coverage():
    assert pages_found(["46", "10", "11", "12", "13"], {"46", "47"}) == "1/2"
    assert pages_found(["46", "47", "11", "12", "13"], {"46", "47"}) == "2/2"
