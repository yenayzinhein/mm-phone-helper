"""Tests for the English -> polite Burmese pipeline (offline paths only)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from translate import translate_to_polite, split_utterance
from politeness import MALE, FEMALE


@pytest.mark.parametrize("english", [
    "Hello",
    "Sorry, I can't hear you very well.",
    "Could you say that again?",
    "We will call you back tomorrow morning.",
    "I'll call you back tomorrow.",
    "Thank you so much for your help.",
    "Please hold on a moment.",
    "What is your name?",
])
@pytest.mark.parametrize("gender", [MALE, FEMALE])
def test_known_phrases_yield_polite_answers(english, gender):
    d = translate_to_polite(english, gender, online=False)
    assert d["burmese"].strip()
    assert "ပါ" in d["burmese"] or "ကဲ့" in d["burmese"], d
    assert d["source"] in ("phrasebook", "glossary", "fallback")
    if gender == MALE:
        assert "ခင်ဗျာ" in d["burmese"], d
    else:
        assert "ရှင်" in d["burmese"], d
        assert "ခင်ဗျာ" not in d["burmese"], d


def test_offline_never_crashes():
    for junk in ["", "   ", "asdf qwer zxcv", "12345", "!@#$%", "a" * 900]:
        d = translate_to_polite(junk, MALE, online=False)
        assert isinstance(d["burmese"], str)


def test_glossary_fallback_is_labelled():
    d = translate_to_polite("the invoice for your account is overdue", MALE, online=False)
    assert d["source"] in ("glossary", "fallback")
    assert d["hint"]


def test_split_utterance_breaks_sentences():
    u = "Hello, this is Anna. Your payment is late. We will call you back tomorrow."
    parts = split_utterance(u)
    assert len(parts) >= 3, parts


def test_split_utterance_breaks_on_and():
    parts = split_utterance("Your card was declined and we need you to call the bank.")
    assert len(parts) == 2, parts


def test_multi_sentence_returns_multiple_answers():
    u = ("Hello, this is Anna. I can't hear you. "
         "We will call you back tomorrow morning.")
    d = translate_to_polite(u, MALE, online=False)
    assert len(d["answers"]) >= 2, d["answers"]
    assert all("ပါ" in a["burmese"] or "ကဲ့" in a["burmese"] for a in d["answers"])


def test_caller_is_not_relabelled_as_me():
    """'I am calling about the invoice' must not become 'ကျွန်တော် ... ဖြစ်ပါတယ်'."""
    d = translate_to_polite("I am calling about the invoice for your account.",
                            MALE, online=False)
    assert "ဖြစ်ပါတယ်" not in d["burmese"], d


def test_direction_of_call_back_is_preserved():
    them = translate_to_polite("We will call you back tomorrow morning.", MALE, online=False)
    assert them["answers"][0]["intent"] == "They will call you back", them["answers"][0]
    me = translate_to_polite("I'll call you back tomorrow.", MALE, online=False)
    assert me["answers"][0]["intent"] == "I'll call you back", me["answers"][0]
    assert them["burmese"] != me["burmese"]


def test_answer_shape_is_stable():
    d = translate_to_polite("hello", MALE, online=False)
    for key in ("english", "burmese", "literal", "source", "hint", "roman",
                "changed", "answers"):
        assert key in d, key


# --------------------------------------------------------------------------
# machine-translation cleanup
# --------------------------------------------------------------------------

from translate import _tidy_burmese, _self_form


def test_tidy_removes_space_before_burmese_full_stop():
    assert _tidy_burmese("မရနိုင်ပါ ခင်ဗျာ ။") == "မရနိုင်ပါ ခင်ဗျာ။"
    assert _tidy_burmese("ကောင်း  ပါ  တယ်") == "ကောင်း ပါ တယ်"


def test_tidy_is_idempotent():
    src = "သင် ၏ အထုပ်ကို ယနေ့ ပို့ဆောင် ၍ မရနိုင်ပါ ။"
    once = _tidy_burmese(src)
    assert _tidy_burmese(once) == once


def test_kyunup_becomes_spoken_pronoun():
    assert _self_form("ကျွန်ုပ် ခေါ်ဆိုနေပါသည်", MALE) == "ကျွန်တော် ခေါ်ဆိုနေပါသည်"
    assert _self_form("ကျွန်ုပ် ခေါ်ဆိုနေပါသည်", FEMALE) == "ကျွန်မ ခေါ်ဆိုနေပါသည်"
    assert _self_form("ကျနော် လာမယ်", MALE) == "ကျွန်တော် လာမယ်"


def test_tidy_reattaches_postpositions():
    # postpositions re-attach; ordinary spaces between words are left alone,
    # because Burmese does use a space as a clause break
    assert _tidy_burmese("သင် ၏ အထုပ် ကို ပို့မရပါ ။") == "သင်၏အထုပ်ကိုပို့မရပါ။"
    assert _tidy_burmese("ကောင်း ပါ တယ်") == "ကောင်း ပါ တယ်"


def test_tidy_keeps_real_word_spaces():
    src = "ငွေပေးချေမှုသည် ရက်ပေါင်း ၃၀ ကျော်ကြာသည်။"
    assert _tidy_burmese(src) == src


def test_full_pipeline_output_has_no_detached_postposition():
    """Whatever the MT engine returns must not reach the user as 'သင် ၏'."""
    from translate import _tidy_burmese, _self_form
    raw = "သင် ၏ အကောင့် အတွက် ငွေတောင်းခံလွှာ အကြောင်း ကျွန်ုပ် ခေါ် နေ ပါ သည် ။"
    out = _self_form(_tidy_burmese(raw), MALE)
    assert " ၏ " not in out
    assert "ကျွန်ုပ်" not in out
    assert "ကျွန်တော်" in out
