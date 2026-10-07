"""Tests for the Burmese politeness engine."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest

from politeness import (
    to_polite, match_template, phrasebook, particles, detect_type, MALE, FEMALE,
)


# ---------------------------------------------------------------------------
# word-boundary safety: the bug that the first draft had
# ---------------------------------------------------------------------------

def test_ko_taw_is_not_split():
    """ကိုယ်တော် must survive intact - it is an honorific, not ကိုယ် + တော်."""
    out = to_polite("ကိုယ်တော် ကြွပါ", MALE)["text"]
    assert "ကိုယ်တော်" in out
    assert "ကျွန်တော်တော်" not in out


def test_min_ko_replaced_whole():
    """မင်းကို -> ခင်ဗျာ (the object marker ကို has to survive)."""
    out = to_polite("မင်းကို ဖုန်းဆက်မယ်", MALE)["text"]
    assert "မင်း" not in out
    assert "ခင်ဗျာ" in out
    assert "ကို" in out


def test_min_the_honorific_untouched():
    """မင်းသား (actor/prince) must not become ခင်ဗျာသား."""
    out = to_polite("မင်းသား လာမယ်", MALE)["text"]
    assert "ခင်ဗျာသား" not in out


# ---------------------------------------------------------------------------
# polite marker + final particle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gender,final", [(MALE, "ခင်ဗျာ"), (FEMALE, "ရှင်")])
def test_final_particle_always_present(gender, final):
    for src in ["ငါ မင်းကို ဖုန်းဆက်မယ်", "မင်း စောင့်နေနော်", "ငါ နားမလည်ဘူး",
                "မင်း ဘယ်သူလဲ"]:
        out = to_polite(src, gender)["text"]
        assert final in out, (src, out)
        assert "ပါ" in out, (src, out)


def test_tal_becomes_pa_tal_male():
    out = to_polite("ငါ ဖုန်းဆက်မယ်", MALE)["text"]
    assert out == "ကျွန်တော် ဖုန်းဆက်မယ်ပါ ခင်ဗျာ။"


def test_tal_becomes_pa_tal_female():
    out = to_polite("ငါ ဖုန်းဆက်မယ်", FEMALE)["text"]
    assert out == "ကျွန်မ ဖုန်းဆက်မယ်ပါ ရှင်။"


def test_casual_naw_replaced():
    out = to_polite("မင်း စောင့်နေနော်", MALE)["text"]
    assert "နော်" not in out
    assert out == "ခင်ဗျာ စောင့်နေပါ ခင်ဗျာ။"


def test_negative_bu_gets_pa():
    out = to_polite("ငါ နားမလည်ဘူး", MALE)["text"]
    assert out == "ကျွန်တော် နားမလည်ဘူးပါ ခင်ဗျာ။"


def test_already_polite_only_gets_final_particle():
    out = to_polite("ကျွန်တော် နားလည်ပါပြီ", MALE)["text"]
    assert out == "ကျွန်တော် နားလည်ပါပြီ ခင်ဗျာ။"


def test_already_polite_female():
    out = to_polite("ကျွန်မ နားလည်ပါပြီ", FEMALE)["text"]
    assert out == "ကျွန်မ နားလည်ပါပြီ ရှင်။"
    assert "ခင်ဗျာ" not in out


def test_request_gets_pa():
    out = to_polite("မင်း ထပ်ပြောပေး", MALE)["text"]
    assert "ထပ်ပြောပေးပါ" in out
    assert out.endswith("ခင်ဗျာ။")


def test_multiple_sentences_each_get_particle():
    src = "ငါ နားမလည်ဘူး။ မင်း ထပ်ပြောပေး။"
    out = to_polite(src, MALE)["text"]
    sentences = [x for x in out.split("။") if x.strip()]
    assert len(sentences) == 2
    # every sentence closes with the male particle
    assert all(x.strip().endswith("ခင်ဗျာ") for x in sentences), out
    assert "မင်း" not in out and "ငါ" not in out


def test_empty_input():
    assert to_polite("", MALE)["text"] == ""
    assert to_polite(None, MALE)["text"] == ""


def test_note_explains_register():
    assert "ရှင်" in to_polite("ငါ လာမယ်", FEMALE)["note"]
    assert "ခင်ဗျာ" in to_polite("ငါ လာမယ်", MALE)["note"]


# ---------------------------------------------------------------------------
# machine-translation input safety
# ---------------------------------------------------------------------------

def test_thin_is_not_swapped():
    """MT renders "your" as သင်၏ -- that is the listener, not the caller."""
    out = to_polite("သင်၏ အထုပ်ကို ယနေ့ ပို့ဆောင်၍ မရနိုင်ပါ", MALE)["text"]
    assert "ခင်ဗျာ၏" not in out
    assert "သင်၏" in out
    assert out.rstrip("။").endswith("ခင်ဗျာ")


def test_long_mt_sentence_keeps_meaning_and_adds_particle():
    src = "သင်၏ ငွေပေးချေမှုသည် ရက်သုံးဆယ် ကျော်လွန်နေပါပြီ"
    out = to_polite(src, MALE)["text"]
    assert "ငွေပေးချေမှု" in out
    assert out.rstrip("။").endswith("ခင်ဗျာ")
    assert "ပါပါ" not in out


def test_nga_in_mt_text_is_upgraded():
    out = to_polite("ငါ ဒီမှာ ရောက်နေတယ်", MALE)["text"]
    assert out == "ကျွန်တော် ဒီမှာ ရောက်နေပါတယ် ခင်ဗျာ။"


# ---------------------------------------------------------------------------
# sentence type detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("s,expected", [
    ("မင်း ဘယ်သူလဲ", "question"),
    ("မင်း ထပ်ပြောပေး", "request"),
    ("ငါ နားမလည်ဘူး", "statement"),
])
def test_detect_type(s, expected):
    assert detect_type(s) == expected


# ---------------------------------------------------------------------------
# template bank
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("english,label", [
    ("hello", "Hello"),
    ("Hello!", "Hello"),
    ("good morning", "Hello"),
    ("Who is this?", "Who is this?"),
    ("Sorry I can't hear you", "I can't hear you"),
    ("I cannot hear you right now", "I can't hear you"),
    ("I don't understand what you said", "I don't understand"),
    ("Can you say that again?", "Please say that again"),
    ("Please speak more slowly", "Please say that again"),
    ("Pardon?", "Please say that again"),
    ("Could you spell that for me?", "Could you spell that?"),
    ("I understand", "I understand"),
    ("Yes", "Yes"),
    ("No", "No"),
    ("Thank you very much", "Thank you"),
    ("I'm sorry", "Sorry"),
    ("Please hold on a moment", "Please hold"),
    ("I'll call you back", "I'll call you back"),
    ("Can I speak to the manager", "May I speak to …"),
    # the caller is introducing *themselves* -> acknowledge, never claim the name
    ("This is Aung speaking", "Caller introducing themselves"),
    ("Hello, this is Sarah from customer support", "Caller introducing themselves"),
    ("I think you have the wrong number", "Wrong number"),
    ("Can you take a message?", "Take a message"),
    ("What is your name?", "What is your name?"),
    ("What's your email address?", "Email"),
    ("Okay, goodbye", "Goodbye"),
    ("How are you?", "How are you?"),
    ("What time is the meeting?", "What time?"),
    ("Please send me the file", "Please send it"),
    ("Can you help me?", "Can you help?"),
    ("There is a problem with my account", "There is a problem"),
    ("I'm not available right now", "Not available"),
    ("How much does it cost?", "How much?"),
    ("You're breaking up, the line is bad", "The line is bad"),
    ("Do you speak Burmese?", "Do you speak Burmese?"),
    ("Sorry I'm in a meeting right now", "I can't talk now"),
])
def test_template_matches(english, label):
    m = match_template(english, MALE)
    assert m is not None, english
    assert m["english"] == label


def test_template_male_uses_khin_bya():
    m = match_template("hello", MALE)
    assert m["burmese"] == "မင်္ဂလာပါ ခင်ဗျာ။"


def test_template_female_uses_shin():
    m = match_template("hello", FEMALE)
    assert m["burmese"] == "မင်္ဂလာပါ ရှင်။"
    assert "ခင်ဗျာ" not in m["burmese"]


def test_template_female_pronoun():
    m = match_template("I can't hear you", FEMALE)
    assert "ရှင်" in m["burmese"]


def test_named_group_captured():
    m = match_template("Can I speak to the manager", MALE)
    assert "Manager" in m["burmese"] or "manager" in m["burmese"].lower()


def test_unmatched_returns_none():
    assert match_template("The quarterly depreciation schedule is amortised", MALE) is None
    assert match_template("", MALE) is None


# ---------------------------------------------------------------------------
# every bank entry must render cleanly and stay polite
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gender", [MALE, FEMALE])
def test_whole_phrasebook_is_polite(gender):
    from politeness import _is_polite
    p = particles(gender)
    rows = phrasebook(gender)
    assert len(rows) >= 25
    for row in rows:
        b = row["burmese"]
        assert b.strip(), row
        assert _is_polite(b), row          # carries ပါ or ကဲ့
        assert p["final"] in b, row        # closes with the speaker particle
        assert "{" not in b and "}" not in b, row
        # the male bank must never leak the female particle
        if gender == MALE:
            # NB: cannot assert "ရှင်" is absent -- it is a real Burmese word
            # (ရှင်းလင်းစွာ).  Assert the female *particle* placement instead.
            assert not b.rstrip("။").rstrip().endswith("ရှင်"), row


def test_whole_phrasebook_survives_the_converter(gender=MALE):
    """Running the converter over its own output must be idempotent-ish:
    no double particles, no crash."""
    for row in phrasebook(MALE):
        again = to_polite(row["burmese"], MALE)["text"]
        assert "ပါပါ" not in again, again
        assert "ခင်ဗျာ ခင်ဗျာ" not in again, again


def test_female_bank_uses_shin_not_khin_bya():
    for row in phrasebook(FEMALE):
        assert "ခင်ဗျာ" not in row["burmese"], row
        assert "ရှင်" in row["burmese"], row
