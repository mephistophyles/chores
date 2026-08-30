from chores.seed import DEFAULT_CONFIG


def test_every_default_category_has_a_known_cycle():
    for _, cycle, _ in DEFAULT_CONFIG:
        assert cycle in {"daily", "weekly", "monthly", "none"}


def test_defaults_have_chores_and_unique_names():
    names = [name for name, _, _ in DEFAULT_CONFIG]
    assert len(names) == len(set(names))
    for _, _, chores in DEFAULT_CONFIG:
        assert chores
        assert all(c.strip() for c in chores)
