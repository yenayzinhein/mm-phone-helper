"""
Burmese politeness engine (offline, deterministic, unit tested).

Responsibilities
----------------
1. `to_polite(text, gender)`  -- rebuild any Burmese sentence (machine
   translated, spoken, or typed casually) into a polite/formal register.
2. `TEMPLATE_BANK` / `match_template()` -- curated polite answers for the
   phrases that actually come up on inbound English phone calls.

Design notes
------------
Burmese has no spaces between words, so every substitution here is done with
an explicit "Myanmar word boundary" regex: a replacement only fires when the
target is not glued to another Myanmar syllable on either side.  That is what
stops `ကိုယ်တော်` being split into `ကိုယ်` + `တော်`, which was the bug in the
first draft of this module.
"""

from __future__ import annotations

import re
import unicodedata

MALE = "male"
FEMALE = "female"

# Myanmar Unicode block: U+1000 - U+109F  (plus extended-A U+AA60 - U+AA7F)
_MM = "\u1000-\u109f\uaa60-\uaa7f"
B = rf"(?<![{_MM}])"   # left Myanmar word boundary
E = rf"(?![{_MM}])"    # right Myanmar word boundary


def _wb(pattern: str) -> str:
    """Wrap a literal Myanmar token so it only matches on word boundaries."""
    return B + re.escape(pattern) + E


# --------------------------------------------------------------------------
# Speaker particles
# --------------------------------------------------------------------------

def particles(gender: str) -> dict:
    """`self`/`you` are the pronouns to use; `final` is the sentence-final
    politeness particle that closes a formal utterance."""
    if gender == FEMALE:
        return {"self": "ကျွန်မ", "you": "ရှင်", "final": "ရှင်",
                "yes": "ဟုတ်ကဲ့ ရှင်"}
    return {"self": "ကျွန်တော်", "you": "ခင်ဗျာ", "final": "ခင်ဗျာ",
            "yes": "ဟုတ်ကဲ့ ခင်ဗျာ"}


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# --------------------------------------------------------------------------
# Substitution tables
# --------------------------------------------------------------------------

# first person -> ကျွန်တော် / ကျွန်မ   (longest first so ကျွန်တော် is not eaten)
FIRST_PERSON = ["ကျွန်တော်", "ငါတို့", "ငါ့", "ငါ", "မိမိ"]

# second person / casual address -> ခင်ဗျာ / ရှင်
# (casual form, replacement) -- the case markers ကို / ရဲ့ are kept on the
# polite form so "မင်းကို" becomes "ခင်ဗျာကို", not "ခင်ဗျာ".
SECOND_PERSON = [
    ("မင်းတို့", "{you}တို့"),
    ("မင်းကို", "{you}ကို"),
    ("မင်းရဲ့", "{you}ရဲ့"),
    ("မင်း", "{you}"),
    ("နင်တို့", "{you}တို့"),
    ("နင့်", "{you}ရဲ့"),
    ("နင်", "{you}"),
    ("ကောင်လေး", "{you}"),
    ("ကောင်မလေး", "{you}"),
    ("ကောင်", "{you}"),
]

# Words that merely *contain* a casual pronoun, or that are already in a formal
# register, are left untouched (မင်းသား = actor, ကိုယ်တော် = honorific "I").
PROTECTED = ["မင်းသား", "မင်းသမီး", "မင်းနေရာ", "ငါး", "ငါးပိ", "ငါးရံ့",
             "ကိုယ်တော်", "ကိုယ်တော်တို့", "တပည့်တော်"]

# "you/your" in machine-translated text refers to the *Burmese listener*, not
# to the caller, so it must never be swapped for ခင်ဗျာ/ရှင်.
CALLER_SIDE = ["သင်", "သင့်", "သင်တို့", "မိမိ"]

# casual clause-final particles -> polite equivalents
FINAL_CASUAL_TO_POLITE = [
    ("တယ်နော်", "ပါတယ်"), ("တယ်ကွ", "ပါတယ်"), ("တယ်နဲ့", "ပါတယ်"),
    ("တယ်ကွာ", "ပါတယ်"), ("ဘူးကွ", "ဘူးပါ"), ("ဘူးနော်", "ဘူးပါ"),
    ("ပြီနော်", "ပြီပါ"), ("ပြီကွ", "ပြီပါ"), ("မယ်နော်", "မယ်ပါ"),
    ("မယ်ကွ", "မယ်ပါ"), ("မှာနော်", "မှာပါ"), ("လို့နော်", "လို့ပါ"),
    ("နေနော်", "နေပါ"), ("တာနော်", "တာပါ"), ("လားကွ", "လား"),
    ("နဲ့နော်", "ပါ"), ("ရဲ့နော်", "ရဲ့ပါ"),
]

# pure interjections that must never survive in formal speech
STRIP_PARTICLES = ["ကွာ", "ကွ", "နော်", "ဗျ", "ဗျာ", "ရှင့်", "ဟဲ့", "ဟေ့"]

# Politeness particles.  Presence anywhere in the clause is enough -- Burmese
# has no word separators and the particle is frequently followed by another
# syllable ("ပါပြီ", "ပါတယ်"), so a right-hand Myanmar boundary would reject
# exactly the sentences we most want to recognise.  False positives are words
# such as ပါဝင် ("to take part"); they are rare in call audio and the fallback
# (only adding the final particle) is harmless.
POLITE_PARTICLES = ("ပါ", "ပါ့", "ကဲ့")

# --------------------------------------------------------------------------
# Sentence-type detection
# --------------------------------------------------------------------------

QUESTION_ENDINGS = ("လား", "လဲ")
REQUEST_ENDINGS = ("ပေး", "လိုက်", "ထား", "ပေးပါ", "ချ", "တောင်း", "ခေါ်", "ပြော")


def detect_type(sentence: str) -> str:
    s = sentence.strip().rstrip("။!?…")
    if s.endswith(QUESTION_ENDINGS):
        return "question"
    if s.endswith(REQUEST_ENDINGS):
        return "request"
    return "statement"


def _is_polite(sentence: str) -> bool:
    return any(m in sentence for m in POLITE_PARTICLES)


# --------------------------------------------------------------------------
# The converter
# --------------------------------------------------------------------------

def to_polite(text: str, gender: str = MALE) -> dict:
    """Rebuild `text` (Burmese) in a polite register.

    Returns ``{"text": str, "changed": [str], "note": str}``.
    """
    p = particles(gender)
    src = _norm(text)
    if not src:
        return {"text": "", "changed": [], "note": ""}

    changes: list[str] = []
    out: list[str] = []

    for raw in re.split(r"(?<=[။!?])|\n", src):
        s = _norm(raw)
        if not s:
            continue

        # A word that merely contains a casual pronoun (မင်းသား) is left alone,
        # and so is any sentence that already addresses the listener as သင်.
        protected = any(w in s for w in PROTECTED + CALLER_SIDE)

        # ---- pronouns ------------------------------------------------
        if not protected:
            for token in FIRST_PERSON:
                if token in (p["self"],):
                    continue
                rx = re.compile(_wb(token))
                if rx.search(s):
                    s = rx.sub(p["self"], s)
                    changes.append(f"{token} → {p['self']}")

            for token, repl in SECOND_PERSON:
                rx = re.compile(_wb(token))
                if rx.search(s):
                    s = rx.sub(repl.format(you=p["you"]), s)
                    changes.append(f"{token} → {repl.format(you=p['you'])}")

        # ---- casual particles ----------------------------------------
        for casual, polite in FINAL_CASUAL_TO_POLITE:
            if casual in s:
                s = s.replace(casual, polite)
                changes.append(f"{casual} → {polite}")

        for particle in STRIP_PARTICLES:
            rx = re.compile(_wb(particle))
            if rx.search(s):
                s = rx.sub("", s).strip()
                changes.append(f"{particle} ဖယ်ရှား")

        s = _norm(s)

        # ---- guarantee a polite verbal marker ------------------------
        if not _is_polite(s):
            stype = detect_type(s)
            body = s.rstrip("။!?…")
            if stype == "question" and body.endswith(QUESTION_ENDINGS):
                changes.append("မေးခွန်းပုံစံ ထိန်းသိမ်း")
            elif stype == "request":
                body = body + "ပါ"
                changes.append("တောင်းဆိုမှု → …ပါ")
            elif body.endswith("တယ်"):
                body = body[:-3] + "ပါတယ်"
                changes.append("…တယ် → …ပါတယ်")
            elif body.endswith("မယ်"):
                body = body + "ပါ"
                changes.append("…မယ် → …မယ်ပါ")
            elif body.endswith(("ဘူး", "ပြီ", "ချင်", "နိုင်", "ရမယ်", "မှာ")):
                body = body + "ပါ"
                changes.append("…ပါ ထည့်")
            else:
                body = body + " ပါ"
                changes.append("ပါ ထည့်")
            s = body

        # ---- sentence-final speaker particle -------------------------
        body = s.rstrip("။!?… ")
        # `endswith("ပါ")` is NOT enough: "နားလည်ပါပြီ" ends in ပြီ even
        # though the polite ပါ is already there.  Check for the particle as a
        # whole syllable instead.
        if not _is_polite(body):
            body = body + " ပါ"
            changes.append("ပါ ထည့်")
        if not body.rstrip().endswith(p["final"]):
            body = body + " " + p["final"]
            changes.append(f"{p['final']} ထည့်")
        s = body + "။"
        out.append(s)

    return {"text": " ".join(out).strip(), "changed": _dedupe(changes),
            "note": _build_note(gender, changes)}


def _dedupe(items):
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _build_note(gender: str, changes) -> str:
    if gender == FEMALE:
        head = "အမျိုးသမီးဖြစ်၍ “ကျွန်မ … ပါ ရှင်” ပုံစံဖြင့် ပြောပါ။"
    else:
        head = "အမျိုးသားဖြစ်၍ “ကျွန်တော် … ပါ ခင်ဗျာ” ပုံစံဖြင့် ပြောပါ။"
    if not changes:
        head += " ဒီစာကြောင်းက ယဉ်ကျေးသော ပုံစံ ဖြစ်ပြီးသားပါ။"
    return head


# --------------------------------------------------------------------------
# Curated phrasebook for inbound English calls
# --------------------------------------------------------------------------
# (regex on lower-cased English, English label, Burmese male, Burmese female,
#  when-to-use hint, romanised pronunciation help)

TEMPLATE_BANK = [
    # -- can't hear / can't understand (checked BEFORE sorry / yes / no) ----
    (r"(can ?'?t|cannot|couldn'?t) (hear|catch|make out)",
     "I can't hear you",
     "တစ်ဆိတ်လောက် ထပ်ပြောပေးပါ {final}။ အသံ ကောင်းစွာ မကြားရပါ။",
     "တစ်ဆိတ်လောက် ထပ်ပြောပေးပါ ရှင်။ အသံ ကောင်းစွာ မကြားရပါ။",
     "အသံမကြားရသည့်အခါ", "tit hsate laung htat pyaw pay-ba"),

    (r"(don'?t|do not|didn'?t) understand|not (get|getting|catching) (it|you|that)|didn'?t (get|catch) that",
     "I don't understand",
     "တစ်ဆိတ် ရှင်းလင်းစွာ ထပ်ပြောပေးပါ {final}။ နားမလည်သေးပါ။",
     "တစ်ဆိတ် ရှင်းလင်းစွာ ထပ်ပြောပေးပါ ရှင်။ နားမလည်သေးပါ။",
     "အင်္ဂလိပ်လို နားမလည်သည့်အခါ", "na ma le the ba"),

    (r"(?!(?:.*\bcan ?'?t|.*\bcannot).*\bhear\b)(?:(say|tell) (it |that |me )?(again|one more time)|repeat (that|it|after me)|pardon\??$|come again\??$|beg your pardon|speak (english |a little |a bit |more )?slow(ly|er)?|slow down)",
     "Please say that again",
     "တစ်ချီလောက် ထပ်ပြောပေးပါ {final}။",
     "တစ်ချီလောက် ထပ်ပြောပေးပါ ရှင်။",
     "ထပ်မေးလိုသည့်အခါ", "tit chi laung htat pyaw pay-ba"),

    (r"spell(ing)?( that| it| out)?",
     "Could you spell that?",
     "စာလုံးပေါင်းကို တစ်လုံးချင်း ပြောပေးပါ {final}။",
     "စာလုံးပေါင်းကို တစ်လုံးချင်း ပြောပေးပါ ရှင်။",
     "အမည်/အီးမေးလ် မေးသည့်အခါ", "sa lone paung ko"),

    # -- phone handling -----------------------------------------------------
    (r"hold (on|the line)|wait (a|one)? ?(moment|second|minute)|one moment|just a sec",
     "Please hold", "ခဏလေး စောင့်ဆိုင်းပေးပါ {final}။",
     "ခဏလေး စောင့်ဆိုင်းပေးပါ ရှင်။", "စောင့်ခိုင်းသည့်အခါ", "kha na lay saung hsain pay-ba"),

    (r"(i'?ll|i will|let me) (call|phone|ring) (you )?back|(i'?ll|i will) get back to (you|me)",
     "I'll call you back", "ကျွန်တော် ပြန်လည် ဆက်သွယ်ပါမယ် {final}။",
     "ကျွန်မ ပြန်လည် ဆက်သွယ်ပါမယ် ရှင်။",
     "ကိုယ်တိုင် ပြန်ခေါ်မည်ဆိုလျှင်", "... pyan lel set thwal ba-me"),

    (r"\b(we'?ll|we will|they'?ll|they will|i'?ll|i will|he'?ll|she'?ll|someone will|our team will) (call|phone|ring|contact) (you |me )?(back|again|later|tomorrow|shortly)",
     "They will call you back", "ဟုတ်ကဲ့။ ပြန်လည် ဆက်သွယ်ပေးပါ {final}။",
     "ဟုတ်ကဲ့။ ပြန်လည် ဆက်သွယ်ပေးပါ ရှင်။",
     "ဖက်ဘက်က ပြန်ခေါ်မည်ဆိုလျှင်", "hoat ke ... pyan lel set thwal pay-ba"),

    (r"(can|may|could) i (speak|talk) (to|with) (?P<who>[\w .']+)",
     "May I speak to …",
     "{who} ကို ခေါ်ပေးပါ {final}။", "{who} ကို ခေါ်ပေးပါ ရှင်။",
     "လူတစ်ဦးကို တောင်းဆို", "… ko khaw pay-ba"),

    (r"wrong (number|person)",
     "Wrong number", "ဖုန်းနံပါတ် လွဲနေပါသလား {final}။",
     "ဖုန်းနံပါတ် လွဲနေပါသလား ရှင်။", "နံပါတ်လွဲလျှင်", "phone number lwe ne ba tha lar"),

    (r"(take|leave|give) (me )?(a )?message",
     "Take a message", "မှတ်ချက်လေး ရေးပေးပါ {final}။",
     "မှတ်ချက်လေး ရေးပေးပါ ရှင်။", "မှတ်ချက်ယူ", "hmat chet lay yay pay-ba"),

    (r"(e-?mail|email address)",
     "Email", "အီးမေးလ်လိပ်စာကို ပြောပေးပါ {final}။",
     "အီးမေးလ်လိပ်စာကို ပြောပေးပါ ရှင်။", "အီးမေးလ်မေး", "e-mel leik sa ko"),

    (r"what('s| is) your (name|company|number)",
     "What is your name?", "နာမည်ကို ပြောပြပေးပါ {final}။",
     "နာမည်ကို ပြောပြပေးပါ ရှင်။", "အမည်မေး", "na me ko pyaw pyay pay-ba"),

    # "This is Anna" is the CALLER introducing themselves.  On a recording the
    # "I" is never the Burmese user, so this must NOT become
    # "ကျွန်တော် Anna ဖြစ်ပါတယ်" -- acknowledge instead.
    (r"^(?:hello[, ]*|hi[, ]*|good (?:morning|afternoon|evening)[, ]*)?this is (?!me\b)(?!(?:a|an|the|my|our|your|his|her|it|that|who)\b)[\w']+",
     "Caller introducing themselves", "ဟုတ်ကဲ့ {final}။", "ဟုတ်ကဲ့ ရှင်။",
     "ဖက်ဘက်က မိမိအမည် ပြောသည့်အခါ", "hoat ke"),

    (r"who('s| is) (this|that)( calling)?[? ]*$",
     "Who is this?", "{self} (အမည်) ဖြစ်ပါတယ် {final}။",
     "ကျွန်မ (အမည်) ဖြစ်ပါတယ် ရှင်။",
     "(အမည်) နေရာတွင် မိမိအမည် ထည့်ပြောပါ", "… pyit-ba-de"),

    # -- closing ------------------------------------------------------------
    (r"(hang up|good ?bye|bye\b|talk (to|with) you later|talk later|have a good (day|one)|that'?s all|i'?ll let you go)",
     "Goodbye", "ကျေးဇူးတင်ပါတယ်။ နောက်မှ ပြန်ဆက်သွယ်ပါမယ် {final}။",
     "ကျေးဇူးတင်ပါတယ်။ နောက်မှ ပြန်ဆက်သွယ်ပါမယ် ရှင်။",
     "ဖုန်းချသည့်အခါ", "kyay-zu tin-ba-de … pyan set thwal ba-me"),

    (r"thank( you|s)?",
     "Thank you", "ကျေးဇူးအထူးတင်ပါတယ် {final}။", "ကျေးဇူးအထူးတင်ပါတယ် ရှင်။",
     "ကျေးဇူးတင်ခြင်း", "kyay-zu a-htu tin-ba-de"),

    (r"(sorry|apolog|my bad|excuse me)",
     "Sorry", "တောင်းပန်ပါတယ် {final}။", "တောင်းပန်ပါတယ် ရှင်။",
     "တောင်းပန်ခြင်း", "taung ban ba-de"),

    # -- short answers (kept late on purpose) -------------------------------
    (r"^(yes|yeah|yep|sure|okay|ok|correct|right|exactly)\b(?!.{0,40}(bye|thank|sorry))",
     "Yes", "ဟုတ်ကဲ့ {final}။", "ဟုတ်ကဲ့ ရှင်။",
     "အတည်ပြုချက်", "hoat ke"),

    (r"^(no|nope|nah)\b(?!.{0,40}(bye|thank|sorry|problem))",
     "No", "မဟုတ်ပါ {final}။", "မဟုတ်ပါ ရှင်။",
     "ငြင်းဆိုချက် (ယဉ်ကျေးစွာ)", "ma hoat ba"),

    (r"(i )?(understand|got it|i see|understood|noted)",
     "I understand", "နားလည်ပါပြီ {final}။", "နားလည်ပါပြီ ရှင်။",
     "နားလည်ကြောင်း အတည်ပြု", "na le ba bi"),

    # -- greetings / small talk --------------------------------------------
    (r"^(hello|hi|hey|good (morning|afternoon|evening|day))[ .,!]*$",
     "Hello", "မင်္ဂလာပါ {final}။", "မင်္ဂလာပါ ရှင်။",
     "ဖုန်းကိုင်သည့်အခါ ပထမဆုံးစကား", "min-ga-lar-ba khin-bya"),

    (r"how are you|how'?s it going|how do you do",
     "How are you?", "ကောင်းပါတယ် {final}။", "ကောင်းပါတယ် ရှင်။",
     "နှုတ်ဆက်စကား", "kaung ba-de"),

    # -- misc ---------------------------------------------------------------
    (r"what (time|day)|which (time|day)|when (is|do|can|will)",
     "What time?", "ဘယ်အချိန်လဲ ပြောပြပေးပါ {final}။",
     "ဘယ်အချိန်လဲ ပြောပြပေးပါ ရှင်။", "အချိန်မေး", "be a-chain le"),

    (r"(send|share|forward) (me )?(it|the|a|that|those)",
     "Please send it", "ပို့ပေးပါ {final}။", "ပို့ပေးပါ ရှင်။",
     "ပို့ခိုင်း", "po pay-ba"),

    (r"(help|assist|support) (me|you|us)?",
     "Can you help?", "ကူညီပေးနိုင်ပါသလား {final}။",
     "ကူညီပေးနိုင်ပါသလား ရှင်။", "အကူအညီတောင်း", "ku nyi pay naing ba tha lar"),

    (r"(problem|issue|mistake|error)",
     "There is a problem", "ပြဿနာလေး ရှိနေပါတယ် {final}။",
     "ပြဿနာလေး ရှိနေပါတယ် ရှင်။", "ပြဿနာရှိကြောင်း", "pyat-sa-na lay shi ne ba-de"),

    (r"(not (available|free)|busy|in a meeting)",
     "Not available", "အဆင်မပြေသေးပါ {final}။", "အဆင်မပြေသေးပါ ရှင်။",
     "အဆင်မပြေကြောင်း", "a-hsin ma pyay the ba"),

    (r"(the )?(line|connection|signal) (is )?(bad|poor|terrible|breaking|cutting)|you'?re breaking up|cutting out",
     "The line is bad", "လိုင်းက မကောင်းပါ {final}။ ပြန်ခေါ်ပေးနိုင်ပါသလား။",
     "လိုင်းက မကောင်းပါ ရှင်။ ပြန်ခေါ်ပေးနိုင်ပါသလား။",
     "လိုင်းမကောင်းသည့်အခါ", "line ka ma kaung ba"),

    (r"(do|can|could) you speak (burmese|myanmar)",
     "Do you speak Burmese?", "မြန်မာလို ပြောလို့ရပါသလား {final}။",
     "မြန်မာလို ပြောလို့ရပါသလား ရှင်။",
     "မြန်မာလို ပြောချင်သည့်အခါ", "myan-mar pyaw lo ya ba tha lar"),

    (r"(i'?m|i am) (in a meeting|driving|busy right now)|can'?t talk (right )?now",
     "I can't talk now", "အခု အဆင်မပြေသေးပါ {final}။ နောက်မှ ပြန်ဆက်သွယ်ပါမယ်။",
     "အခု အဆင်မပြေသေးပါ ရှင်။ နောက်မှ ပြန်ဆက်သွယ်ပါမယ်။",
     "ဖုန်းမပြောနိုင်သည့်အခါ", "a-kha a-hsin ma pyay the ba"),

    (r"(price|cost|how much|fee|charge)",
     "How much?", "ဘယ်လောက်ကျသလဲ ပြောပြပေးပါ {final}။",
     "ဘယ်လောက်ကျသလဲ ပြောပြပေးပါ ရှင်။", "ဈေးနှုန်းမေး", "be lau kya tha le"),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), label, tm, tf, hint, rom)
             for pat, label, tm, tf, hint, rom in TEMPLATE_BANK]


# Leading filler is stripped before matching, so "Sorry, I can't hear you"
# resolves to the "can't hear" intent instead of the apology.
_FILLER = re.compile(
    r"""^(?:(?:o+h|uh+|um+|er+|well|so|anyway|anyways|ok|okay|right|alright|
              hi|hello|hey|sorry|excuse me|pardon|look|listen|please|
              good (?:morning|afternoon|evening|day))[, ]+)+""",
    re.IGNORECASE | re.VERBOSE,
)


def _strip_filler(text: str) -> str:
    """Drop leading conversational filler, but never the whole sentence."""
    stripped = _FILLER.sub("", text.strip())
    return (stripped or text).strip()


def _ranked(text: str, gender: str = MALE):
    """Every bank entry that matches, best first.

    Score = how much of the sentence the pattern explains, plus a bonus for
    matching at the start of the utterance.  A pattern covering the whole
    sentence therefore beats one that catches three words in the middle.
    """
    p = particles(gender)
    low = _strip_filler(_norm(text).lower()).strip(".,!? ").strip()
    if not low:
        return []
    hits = []
    for rx, label, tm, tf, hint, rom in _COMPILED:
        m = rx.search(low)
        if not m:
            continue
        tpl = tm if gender != FEMALE else tf
        named = {k: (v or "").strip() for k, v in m.groupdict().items()}
        named = {k: v[:1].upper() + v[1:] for k, v in named.items() if v}
        vals = {"self": p["self"], "you": p["you"], "final": p["final"]}
        vals.update(named)
        vals.setdefault("who", "...")     # named group wins if it matched
        try:
            rendered = tpl.format(**vals)
        except (KeyError, IndexError):
            continue
        score = (m.end() - m.start()) + (40 if m.start() == 0 else 0)
        hits.append({"score": score, "english": label, "burmese": rendered,
                     "hint": hint, "roman": rom, "matched": True,
                     "span": (m.start(), m.end())})
    hits.sort(key=lambda h: -h["score"])
    return hits


def match_template(text: str, gender: str = MALE):
    """Best-matching curated entry for `text`, or None."""
    hits = _ranked(text, gender)
    if not hits:
        return None
    best = dict(hits[0])
    best.pop("score", None)
    best.pop("span", None)
    return best


def phrasebook(gender: str = MALE):
    """The whole bank, rendered for `gender`, grouped for the UI."""
    p = particles(gender)
    rows = []
    for rx, label, tm, tf, hint, rom in _COMPILED:
        tpl = tm if gender != FEMALE else tf
        try:
            rendered = tpl.format(self=p["self"], you=p["you"], final=p["final"],
                                  who="…")
        except (KeyError, IndexError):
            rendered = tpl
        rows.append({"english": label, "burmese": rendered, "hint": hint,
                     "roman": rom})
    return rows
