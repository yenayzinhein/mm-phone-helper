"""
English -> polite Burmese translation pipeline.

Order of attempts (first hit wins):

1. **Template bank** (offline)  -- curated, hand-checked polite answers for the
   phrases that actually come up on inbound English calls.  Highest quality.
2. **MyMemory MT** (online, optional) -- free, key-less REST endpoint.  Used
   only when the caller says something the bank does not cover.  Its raw output
   is then pushed through `politeness.to_polite`, which is what makes the
   result sound like a Burmese person being polite rather than a translation.
3. **Glossary** (offline) -- word-for-word fallback so the user always gets
   *something* readable when they are offline.

Nothing here is allowed to raise: a phone call does not wait for a stack trace.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request

from politeness import (FEMALE, MALE, _strip_filler, match_template, particles,
                        phrasebook, to_polite)

MEMO_TIMEOUT = 6.0          # seconds -- a phone call cannot wait longer
_cache: dict[str, dict] = {}
_lock = threading.Lock()

MYMEMORY_URL = "https://api.mymemory.translated.net/get?q={q}&langpair=en|my"


# --------------------------------------------------------------------------
# Offline glossary (used only when the network is unavailable)
# --------------------------------------------------------------------------

GLOSSARY = {
    "hello": "မင်္ဂလာပါ", "hi": "မင်္ဂလာပါ", "good": "ကောင်း", "morning": "မနက်",
    "afternoon": "နေ့လယ်", "evening": "ညနေ", "night": "ည",
    "yes": "ဟုတ်ကဲ့", "no": "မဟုတ်ပါ", "please": "ကျေးဇူးပြု၍",
    "thank": "ကျေးဇူးတင်", "thanks": "ကျေးဇူးတင်", "sorry": "တောင်းပန်",
    "name": "နာမည်", "number": "နံပါတ်", "phone": "ဖုန်း", "call": "ခေါ်",
    "speak": "ပြော", "talk": "ပြော", "say": "ပြော", "hear": "ကြား",
    "listen": "နာထောင်", "understand": "နားလည်", "know": "သိ", "wait": "စောင့်",
    "hold": "စောင့်", "moment": "ခဏ", "second": "စက္ကန့်", "minute": "မိနစ်",
    "time": "အချိန်", "day": "နေ့", "today": "ယနေ့", "tomorrow": "မနက်ဖြန်",
    "problem": "ပြဿနာ", "issue": "ကိစ္စ", "help": "ကူညီ", "money": "ငွေ",
    "price": "ဈေးနှုန်း", "cost": "ကုန်ကျ", "pay": "ပေးချေ", "bill": "ဘီးလ်",
    "account": "အကောင့်", "email": "အီးမေးလ်", "address": "လိပ်စာ",
    "company": "ကုမ္ပဏီ", "office": "ရုံး", "meeting": "အစည်းအဝေး",
    "message": "မှတ်ချက်", "again": "ထပ်မံ", "repeat": "ထပ်ပြော",
    "slowly": "ဖြည်းဖြည်း", "slow": "ဖြည်း", "fast": "မြန်",
    "wrong": "လွဲ", "right": "မှန်", "correct": "မှန်ကန်",
    "available": "အဆင်ပြေ", "busy": "အလုပ်ရှုပ်", "later": "နောက်မှ",
    "now": "အခု", "here": "ဒီမှာ", "there": "အဲဒီမှာ",
    "what": "ဘာ", "when": "ဘယ်အချိန်", "where": "ဘယ်နေရာ",
    "who": "ဘယ်သူ", "why": "ဘာကြောင့်", "how": "ဘယ်လို",
    "can": "နိုင်", "cannot": "မရ", "need": "လိုအပ်", "want": "လိုချင်",
    "send": "ပို့", "receive": "လက်ခံ", "check": "စစ်ဆေး", "confirm": "အတည်ပြု",
    "card": "ကတ်", "bank": "ဘဏ်", "order": "အော်ဒါ", "delivery": "ပို့ဆောင်",
    "customer": "ဖောက်သည်", "service": "ဝန်ဆောင်မှု", "line": "လိုင်း",
    "voice": "အသံ", "sound": "အသံ", "clear": "ရှင်းလင်း",
    "welcome": "ကြိုဆို", "goodbye": "နှုတ်ဆက်", "bye": "နှုတ်ဆက်",
}


MY_PUNCT = "\u104a\u104b!?.,;:"


# Burmese postpositions are written attached to the noun ("သင့်အထုပ်ကို"),
# but MT hands them back as separate space-delimited tokens ("သင် ၏ အထုပ် ကို").
_POSTPOSITIONS = ("၏", "အတွက်", "ကြောင့်", "မှာ", "၌", "တွင်", "၍",
                  "၎င်း", "နှင့်", "ကို", "သို့", "လောက်", "ခန့်", "ရဲ့")
_POSTPOS_RX = re.compile(
    r"(?<=[\u1000-\u109f])\s+(" + "|".join(map(re.escape, _POSTPOSITIONS))
    + r")\s*(?=[\u1000-\u109f])"
)


def _tidy_burmese(text: str) -> str:
    """Machine translation arrives with debris: a space before every Burmese
    full stop, detached postpositions, doubled spaces, and the written-style
    pronoun ကျွန်ုပ် which nobody says on a phone call."""
    t = text or ""
    t = re.sub(r"\s+([\u104a\u104b!?.,;:])", r"\1", t)   # space before punctuation
    prev = None
    while prev != t:                                        # postpositions chain
        prev = t
        t = _POSTPOS_RX.sub(lambda m: m.group(1), t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = t.replace("\u200b", "").strip()
    return t


def _self_form(text: str, gender: str) -> str:
    """ကျွန်ုပ် / ကျနော် -> ကျွန်တော် (male) or ကျွန်မ (female)."""
    me = particles(gender)["self"]
    for variant in ("ကျွန်ုပ်တို့", "ကျနော်တို့"):
        text = text.replace(variant, me + "တို့")
    for variant in ("ကျွန်ုပ်", "ကျနော်", "ကျွန်တော်မျာ"):
        text = text.replace(variant, me)
    return text


def _glossary_lookup(english: str) -> str:
    """Word-for-word gloss.  Deliberately labelled as a rough hint in the UI."""
    words = re.findall(r"[A-Za-z']+", english.lower())
    hits = [GLOSSARY[w] for w in words if w in GLOSSARY]
    return " ".join(dict.fromkeys(hits))


# --------------------------------------------------------------------------
# Online MT
# --------------------------------------------------------------------------

def _mymemory(english: str) -> str | None:
    """Best-effort MyMemory en->my.  Returns None on any failure."""
    key = english.strip().lower()
    with _lock:
        if key in _cache:
            return _cache[key]
    url = MYMEMORY_URL.format(q=urllib.parse.quote(english[:450]))
    req = urllib.request.Request(url, headers={"User-Agent": "mm-polite-phone/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=MEMO_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        text = (data.get("responseData") or {}).get("translatedText") or ""
        text = text.strip()
        if not text or text.upper().startswith(("MYMEMORY", "QUERY", "INVALID", "ERROR")):
            text = ""
    except Exception:
        text = ""
    with _lock:
        _cache[key] = text or None
    return text or None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Utterance splitting
# --------------------------------------------------------------------------

_SENT_END = re.compile(r"(?<=[.!?])\s+")
# the comma is optional: "declined and we need ..." splits just as well
_CLAUSE = re.compile(r",?\s+\b(?=(?:and|but|so)\s+\w)|(?:,\s+)(?=(?:we|i|they|he|she|you|it|our)\b)",
                     re.IGNORECASE)


def split_utterance(text: str) -> list[str]:
    """Split a transcript into answerable units.

    Callers ramble: one recording often holds a greeting, the reason for the
    call and an instruction.  Each of those deserves its own polite reply, so
    we split on sentence ends *and* on coordinating conjunctions.
    """
    parts: list[str] = []
    for sent in _SENT_END.split((text or "").strip()):
        sent = sent.strip()
        if sent:
            parts.extend(x.strip() for x in _CLAUSE.split(sent) if x.strip())
    return [p for p in parts if len(p) > 1]


def translate_to_polite(english: str, gender: str = MALE, online: bool = True) -> dict:
    """
    Translate `english` and return the polite Burmese answer to say.

    -> {"english", "burmese", "literal", "source", "hint", "roman", "changed"}
    """
    english = (english or "").strip()
    if not english:
        return {"english": "", "burmese": "", "literal": "", "source": "none",
                "hint": "", "roman": "", "changed": [], "answers": []}

    units = [u for u in split_utterance(english) if _strip_filler(u)]
    if not units:
        units = [english]

    answers, seen, untranslated = [], set(), []
    for unit in units:
        one = _translate_unit(unit, gender, online)
        key = one["burmese"]
        if key and key not in seen:
            seen.add(key)
            answers.append(one)
        if one["source"] in ("glossary", "fallback") and len(unit.split()) > 3:
            untranslated.append(unit)

    if not answers:                       # nothing matched at all
        answers = [_translate_unit(english, gender, online)]

    primary = dict(answers[0])
    primary["english"] = english
    primary["answers"] = answers[:4]
    primary["untranslated"] = untranslated[:4]
    if len(answers) > 1:
        primary["hint"] = ("စာကြောင်း တစ်ကြောင်းချင်းအတွက် အဖြေ "
                           f"{len(answers)} ခု ရှိသည် - အောက်တွင် ကြည့်ပါ။")
    return primary


def _translate_unit(english: str, gender: str, online: bool) -> dict:
    """One sentence in -> one polite Burmese answer out."""
    # 1. curated bank
    hit = match_template(english, gender)
    if hit:
        return {"english": english, "burmese": hit["burmese"], "literal": "",
                "source": "phrasebook", "hint": hit["hint"],
                "roman": hit["roman"], "intent": hit["english"],
                "changed": ["ယဉ်ကျေးသော အသေအချာ စကားလုံးကို သုံးထားသည်"]}

    # 2. machine translation + politeness pass
    literal = _mymemory(english) if online else ""
    if literal:
        literal = _self_form(_tidy_burmese(literal), gender)
        polite = to_polite(literal, gender)
        return {"english": english, "burmese": polite["text"], "literal": literal,
                "source": "mt+polite", "intent": "",
                "hint": "စက်ဘာသာပြန်ကို ယဉ်ကျေးသော ပုံစံ ပြောင်းထားသည်",
                "roman": "", "changed": polite["changed"]}

    # 3. offline glossary
    gloss = _glossary_lookup(english)
    if gloss:
        body = to_polite(gloss, gender)
        return {"english": english, "burmese": body["text"], "literal": gloss,
                "source": "glossary", "intent": "",
                "hint": "အဓိပ္ပာယ်အကြမ်း ဖော်ပြချက်သာ ဖြစ်သည် - အင်တာနက်ရလျှင် ပိုတိကျမည်",
                "roman": "", "changed": body["changed"]}

    # 4. nothing usable -- hand back the safest universal reply
    p = particles(gender)
    return {"english": english,
            "burmese": "တစ်ဆိတ်လောက် ထပ်ပြောပေးပါ " + p["final"] + "။ နားမလည်သေးပါ။",
            "literal": "", "source": "fallback", "intent": "",
            "hint": "ဘာသာပြန်မရ၍ အသုံးအများဆုံး ယဉ်ကျေးသော အဖြေကို ပေးထားသည်",
            "roman": "tit hsate laung htat pyaw pay-ba", "changed": []}


__all__ = ["translate_to_polite", "split_utterance", "to_polite", "phrasebook", "match_template",
           "MALE", "FEMALE"]
