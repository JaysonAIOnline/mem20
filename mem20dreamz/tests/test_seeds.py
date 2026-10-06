"""Tests for cue generation.

The defect these replace was a list of twelve invented sentences handed out with
``index % 12``, and then a second attempt that dressed the estate's backlog up
as inspiration. Both were wrong in kind. These pin the third thing: cues, not
tasks, paired from the estate's own language and never repeated.
"""

import pytest

from mem20dreamz import seeds


def _fake_estate(tmp_path):
    (tmp_path / "mem20alphagraph").mkdir()
    (tmp_path / "mem20alphagraph" / "pyproject.toml").write_text(
        '[project]\nname="mem20alphagraph"\ndescription="graph reasoning for spatial motion"\n'
        'keywords=["graph","spatial","motion"]\n',
        encoding="utf-8",
    )
    (tmp_path / "mem20betasound").mkdir()
    (tmp_path / "mem20betasound" / "pyproject.toml").write_text(
        '[project]\nname="mem20betasound"\ndescription="graph of spatial motion in sound"\n'
        'keywords=["graph","spatial","sound"]\n',
        encoding="utf-8",
    )
    (tmp_path / "mem20gammavoice").mkdir()
    (tmp_path / "mem20gammavoice" / "pyproject.toml").write_text(
        '[project]\nname="mem20gammavoice"\ndescription="voice graphs for spatial motion"\n',
        encoding="utf-8",
    )
    (tmp_path / "mem20deltachain").mkdir()
    (tmp_path / "mem20deltachain" / "pyproject.toml").write_text(
        '[project]\nname="mem20deltachain"\ndescription="spatial chain of sound and voice"\n',
        encoding="utf-8",
    )
    return tmp_path


def test_there_is_no_canned_pool():
    assert not hasattr(seeds, "SEED_POOL")
    source = open(seeds.__file__, encoding="utf-8").read()  # noqa: SIM115 - one read, asserted immediately below
    assert "SEED_POOL" not in source


def test_no_cue_is_a_task():
    """A cue turns something over. It does not instruct."""
    pool = seeds.candidates()
    banned = ("no test suite", "design the smallest", "pyproject.toml", "unverified",
              "unpackaged", "would fail if")
    for _, cue in pool[:400]:
        assert not any(b in cue for b in banned), cue


def test_vocabulary_is_the_estates_own_language(tmp_path):
    _fake_estate(tmp_path)
    vocab = seeds.estate_vocabulary(root=str(tmp_path))
    assert "graph" in vocab
    assert "spatial" in vocab
    assert "sound" in vocab


def test_boilerplate_is_filtered_out(tmp_path):
    """A phrase a dozen packages copied is a template, not a domain word."""
    for i in range(12):
        d = tmp_path / f"mem20crew{i}"
        d.mkdir()
        (d / "pyproject.toml").write_text(
            '[project]\nname="x"\ndescription="crew runtime grouping reviewed packages '
            'for joint integration"\n',
            encoding="utf-8",
        )
    for i, extra in enumerate(("graph", "spatial", "reasoning")):
        d = tmp_path / f"mem20solo{i}"
        d.mkdir()
        (d / "pyproject.toml").write_text(
            f'[project]\nname="y{i}"\ndescription="graph spatial reasoning variant {extra}"\n',
            encoding="utf-8",
        )
    vocab = seeds.estate_vocabulary(root=str(tmp_path))
    assert "graph" in vocab
    for template_word in ("crew", "runtime", "grouping", "reviewed", "joint", "packages"):
        assert template_word not in vocab, f"{template_word} is template, not language"


def test_filenames_do_not_become_words(tmp_path):
    d = tmp_path / "mem20humancapabilitysuperplatformz"
    d.mkdir()
    (d / "pyproject.toml").write_text(
        '[project]\nname="mem20humancapabilitysuperplatformz"\n'
        'description="a platform for human capability"\n',
        encoding="utf-8",
    )
    vocab = seeds.estate_vocabulary(root=str(tmp_path))
    assert "humancapabilit" not in vocab


def test_cues_pair_words_that_have_no_reason_to_meet(tmp_path):
    _fake_estate(tmp_path)
    pool = seeds.candidates(root=str(tmp_path))
    assert pool
    joined = " ".join(cue for _, cue in pool)
    assert "graph" in joined and "sound" in joined


def test_cues_are_unique(tmp_path):
    pool = seeds.candidates(root=str(tmp_path))
    texts = [cue for _, cue in pool]
    assert len(texts) == len(set(texts))


def test_never_repeats_a_cue(tmp_path):
    _fake_estate(tmp_path)
    state: dict = {}
    drawn = [seeds.next_seed(state, root=str(tmp_path)) for _ in range(8)]
    assert len(set(drawn)) == len(drawn)


def test_issued_ledger_persists_in_state(tmp_path):
    _fake_estate(tmp_path)
    state: dict = {}
    first = seeds.next_seed(state, root=str(tmp_path))
    assert state["seeds_issued"] == [first]
    assert state["seed_fingerprints"]
    assert state["seed_index"] == 1


def test_restart_does_not_reissue(tmp_path):
    _fake_estate(tmp_path)
    state: dict = {}
    first = seeds.next_seed(state, root=str(tmp_path))
    reloaded = dict(state)
    second = seeds.next_seed(reloaded, root=str(tmp_path))
    assert second != first


def test_exhaustion_raises_rather_than_repeating(tmp_path):
    _fake_estate(tmp_path)
    pool = seeds.candidates(root=str(tmp_path))
    state: dict = {
        "seed_fingerprints": [fp for fp, _ in pool],
        "seeds_issued": [c for _, c in pool],
    }
    with pytest.raises(seeds.SeedExhausted):
        seeds.next_seed(state, root=str(tmp_path))


def test_no_vocabulary_raises_rather_than_inventing(tmp_path):
    with pytest.raises(seeds.SeedExhausted):
        seeds.next_seed({}, root=str(tmp_path / "empty"))


def test_pool_is_far_larger_than_the_twelve_it_replaced(tmp_path):
    vocab = ("graph", "spatial", "motion", "sound", "voice", "layer", "fold", "mesh",
             "trace", "grain", "bloom", "drift")
    for i in range(4):
        d = tmp_path / f"mem20pkg{i}"
        d.mkdir()
        (d / "pyproject.toml").write_text(
            '[project]\nname="x{}"\ndescription="{}"\n'.format(i, " ".join(vocab[i * 3:i * 3 + 6])),
            encoding="utf-8",
        )
    assert len(seeds.candidates(root=str(tmp_path))) > 12
