import pytest
from finbert_checkpoint_audit import compare,FIXED_BATCH_STARTS


def test_fixed_batch_offsets_not_selected_from_outcomes():
    assert FIXED_BATCH_STARTS==[0,8000,16000,32000,56000]
    assert all(i%32==0 for i in FIXED_BATCH_STARTS)


def test_exact_reproduction_and_tolerance():
    expected={'a':[.2,.3,.5]}
    assert compare(expected,expected)==0
    assert compare(expected,{'a':[.20000001,.29999999,.5]})<1e-7


def test_normalized_but_wrong_scores_do_not_pass():
    with pytest.raises(ValueError,match='not reproduced'):
        compare({'a':[.2,.3,.5]},{'a':[.5,.3,.2]})


def test_missing_headline_does_not_pass():
    with pytest.raises(ValueError,match='membership'):
        compare({'a':[.2,.3,.5]}, {})


def test_nonfinite_score_does_not_pass():
    with pytest.raises(ValueError): compare({'a':[.2,.3,.5]},{'a':[float('nan'),.3,.5]})
