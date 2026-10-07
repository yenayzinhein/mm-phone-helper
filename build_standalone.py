#!/usr/bin/env python3
"""Build `dist/ဖုန်းပြောအကူ.html` -- one self-contained file.

The Flask app needs Python + a 75 MB Whisper model, which is not something you
install on a phone.  The phrasebook and the politeness engine, however, are
pure data and pure string rewriting, so they can be shipped as a single HTML
file with the Padauk webfont base64-inlined.  That file works with no network
at all: open it in any browser, tap a phrase, copy it, read it out.

Everything is pre-rendered in Python from the *same* tables the server uses, so
the offline page can never drift from the API.

Usage:  python3 build_standalone.py
"""

from __future__ import annotations

import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app")
OUT = os.path.join(HERE, "dist")
sys.path.insert(0, APP)

from politeness import FEMALE, MALE, phrasebook          # noqa: E402
from translate import GLOSSARY, split_utterance           # noqa: E402
from politeness import TEMPLATE_BANK                      # noqa: E402

TEMPLATE_PATH = os.path.join(APP, "templates", "index.html")
FONT_DIR = os.path.join(APP, "static", "fonts")


def b64_font(name: str) -> str:
    with open(os.path.join(FONT_DIR, name), "rb") as fh:
        return "data:font/woff2;base64," + base64.b64encode(fh.read()).decode()


def main() -> str:
    html = open(TEMPLATE_PATH, encoding="utf-8").read()
    html = html.replace("/static/fonts/padauk-400.woff2", b64_font("padauk-400.woff2"))
    html = html.replace("/static/fonts/padauk-700.woff2", b64_font("padauk-700.woff2"))

    # data the offline page needs: both phrasebooks + the glossary
    payload = {
        "male": phrasebook(MALE),
        "female": phrasebook(FEMALE),
        "glossary": GLOSSARY,
    }
    data_js = "<script>window.OFFLINE_DATA=" + json.dumps(payload, ensure_ascii=False) + ";</script>"
    html = html.replace("</head>", data_js + "\n</head>")

    # swap the network calls for local lookups
    shim = """
<script>
/* ---------------- offline mode ---------------- */
(function(){
  const D = window.OFFLINE_DATA;
  if(!D) return;
  const state = {gender:'male'};

  // phrasebook comes from the embedded table instead of /api/phrasebook
  window.__offlineRows = () => D[state.gender] || [];

  // "I can't hear you" -> the curated Burmese answer, with no network
  window.__offlineAnswer = (english) => {
    const q = (english||'').toLowerCase().trim();
    if(!q) return null;
    const rows = window.__offlineRows();
    // longest-word-overlap match, which is good enough for the fixed bank
    let best=null, bestScore=0;
    const qw = new Set(q.replace(/[^a-z' ]/g,' ').split(/\\s+/).filter(Boolean));
    rows.forEach(r=>{
      const rw = new Set(r.english.toLowerCase().split(/\\s+/).filter(w=>w.length>2));
      let hit=0; rw.forEach(w=>{ if(qw.has(w)||q.includes(w)) hit++; });
      const score = hit/rw.size;
      if(score>bestScore){ bestScore=score; best=r; }
    });
    if(best && bestScore>=0.5){
      return {english, burmese:best.burmese, roman:best.roman, hint:best.hint,
              source:'phrasebook', literal:'', answers:[{burmese:best.burmese, source:'phrasebook', hint:best.hint, roman:best.roman, english}]};
    }
    return null;
  };

  // intercept fetch() so the existing UI code keeps working unchanged
  const realFetch = window.fetch.bind(window);
  window.fetch = function(url, opts){
    const u = String(url);
    if(u.startsWith('/api/phrasebook')){
      const g = /female/.test(u) ? 'female' : 'male';
      state.gender = g;
      return Promise.resolve(new Response(JSON.stringify({gender:g, rows:D[g]}),
                                          {headers:{'Content-Type':'application/json'}}));
    }
    if(u.startsWith('/api/translate')){
      const g = /female/.test(u) ? 'female' : 'male';
      state.gender = g;
      let text='';
      try{ text = JSON.parse((opts&&opts.body)||'{}').text || ''; }catch(e){}
      const hit = window.__offlineAnswer(text);
      const body = hit || {
        english:text, source:'offline',
        burmese:(g==='female'
          ? 'တစ်ဆိတ်လောက် ထပ်ပြောပေးပါ ရှင်။ နားမလည်သေးပါ။'
          : 'တစ်ဆိတ်လောက် ထပ်ပြောပေးပါ ခင်ဗျာ။ နားမလည်သေးပါ။'),
        hint:'အင်တာနက်မရှိ၍ အခြေခံအဖြေသာ ပေးနိုင်သည်', roman:'', literal:'',
        answers:[]};
      return Promise.resolve(new Response(JSON.stringify(body),
                                          {headers:{'Content-Type':'application/json'}}));
    }
    if(u.startsWith('/api/polish')){
      let text='';
      try{ text = JSON.parse((opts&&opts.body)||'{}').text || ''; }catch(e){}
      return Promise.resolve(new Response(JSON.stringify({input:text, text:text,
        changed:[], note:'offline'}), {headers:{'Content-Type':'application/json'}}));
    }
    if(u.startsWith('/api/transcribe')){
      return Promise.resolve(new Response(JSON.stringify({error:
        'အသံခွဲခြမ်းစိတ်ဖြာခြင်းအတွက် ဆာဗာ လိုအပ်ပါသည်။ စာရိုက်ခြင်း သို့မဟုတ် စကားလုံးစာအုပ်ကို သုံးပါ။'}),
        {status:501, headers:{'Content-Type':'application/json'}}));
    }
    return realFetch(url, opts);
  };

  // the recording button is useless offline -- point it at the phrasebook
  document.addEventListener('DOMContentLoaded', ()=>{
    const hint = document.getElementById('michint');
    if(hint) hint.textContent = 'အော့ဖ်လိုင်းဗားရှင်း - အသံသွင်းခြင်း မရပါ။ စာရိုက်ခြင်း/စကားလုံးစာအုပ်ကို သုံးပါ';
  });
})();
</script>
"""
    html = html.replace("</body>", shim + "\n</body>")
    html = html.replace("<title>ဖုန်းပြော အကူ",
                        "<title>ဖုန်းပြော အကူ (အော့ဖ်လိုင်း)")

    os.makedirs(OUT, exist_ok=True)
    dest = os.path.join(OUT, "ဖုန်းပြောအကူ-offline.html")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(html)
    return dest


if __name__ == "__main__":
    path = main()
    print("built", path, f"({os.path.getsize(path)/1024:.0f} KB)")
