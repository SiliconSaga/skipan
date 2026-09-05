from app.verifier import coverage_warnings, verify_moves

CREWS = [
    {"person_id": "p1", "name": "Ada", "crafts": ["electrician"], "crew": "alpha"},
    {"person_id": "p2", "name": "Bo", "crafts": ["hvac"], "crew": "alpha"},
]
SITES = [
    {"site_id": "s1", "customer_name": "Smith", "needed_crafts": ["electrician"], "needs": ["outdoor"]},
    {"site_id": "wh", "customer_name": "—", "needed_crafts": [], "needs": ["indoor"]},
]
ASSIGNED = [{"row": 2, "person_id": "p1", "site_id": "s1", "note": ""}]


def test_valid_move_and_unassigned_person():
    verified = verify_moves(
        [{"person_id": "p1", "from_site": "s1", "to_site": "wh", "reason": "rain"},
         {"person_id": "p2", "from_site": "", "to_site": "s1", "reason": "cover"}],
        CREWS, SITES, ASSIGNED,
    )
    assert all(v.valid for v in verified)


def test_unknown_person_site_and_from_mismatch():
    verified = verify_moves(
        [{"person_id": "ghost", "from_site": "", "to_site": "s1"},
         {"person_id": "p1", "from_site": "s1", "to_site": "mars"},
         {"person_id": "p2", "from_site": "s1", "to_site": "wh"}],  # p2 is actually unassigned
        CREWS, SITES, ASSIGNED,
    )
    assert [v.valid for v in verified] == [False, False, False]
    assert any("unknown person" in i for i in verified[0].issues)
    assert any("unknown site" in i for i in verified[1].issues)
    assert any("does not match" in i for i in verified[2].issues)


def test_duplicate_person_in_move_set_invalid():
    verified = verify_moves(
        [{"person_id": "p1", "from_site": "s1", "to_site": "wh"},
         {"person_id": "p1", "from_site": "s1", "to_site": "s1"}],
        CREWS, SITES, ASSIGNED,
    )
    assert verified[0].valid is False and any("duplicate" in i for i in verified[0].issues)
    assert verified[1].valid is False and any("duplicate" in i for i in verified[1].issues)


def test_coverage_warns_when_needed_craft_leaves():
    verified = verify_moves([{"person_id": "p1", "from_site": "s1", "to_site": "wh", "reason": "rain"}], CREWS, SITES, ASSIGNED)
    warnings = coverage_warnings(CREWS, SITES, ASSIGNED, verified)
    assert warnings == ["s1: missing craft(s) electrician"]
