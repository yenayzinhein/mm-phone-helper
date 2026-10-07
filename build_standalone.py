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
    /* client-side machine translation + politeness cleanup, so the static
       page still answers sentences the phrasebook does not cover */
    async function onlineMT(text, g){
      try{
        const r = await fetch('https://api.mymemory.translated.net/get?q='
          + encodeURIComponent(text.slice(0,450)) + '&langpair=en|my');
        const d = await r.json();
        let t = (((d||{}).responseData)||{}).translatedText || '';
        t = String(t).trim();
        if(!t || /MYMEMORY|INVALID|ERROR|QUERY/i.test(t)) return null;
        t = t.replace(/\s+([။!?၊;:])/g,'$1').replace(/\s{2,}/g,' ')
             .replace(/​/g,'').trim();
        // reattach detached postpositions exactly like the server engine
        // reattach detached postpositions exactly like the server engine
        // (regex LITERAL -- string-built regexes keep losing a backslash
        //  through the Python/JS escaping layers)
        const RX=/([က-႟])\s+(၏|အတွက်|ကြောင့်|မှာ|၌|တွင်|၍|၎င်း|နှင့်|ကို|သို့|လောက်|ခန့်|ရဲ့)\s*(?=[က-႟])/g;
        let prev=null;
        while(prev!==t){ prev=t; t=t.replace(RX,'$1$2'); }
        const me  = (g==='female') ? 'ကျွန်မ' : 'ကျွန်တော်';
        t = t.replace(/ကျွန်ုပ်တို့/g, me+'တို့').replace(/ကျွန်ုပ်/g, me)
             .replace(/ကျနော်/g, me);
        const fin = (g==='female') ? 'ရှင်' : 'ခင်ဗျာ';
        let body = t.replace(/[။!?]+\s*$/,'');
        if(body.indexOf('ပါ')<0 && body.indexOf('ကဲ့')<0) body += ' ပါ';
        if(!body.endsWith(fin)) body += ' ' + fin;
        return {english:text, burmese: body+'။', literal:t, source:'mt+polite',
                hint:'အင်တာနက်ဘာသာပြန် + ယဉ်ကျေးမှု ပြင်ဆင်ချက်', roman:'',
                changed:[], answers:[]};
      }catch(e){ return null; }
    }

    if(u.startsWith('/api/translate')){
      const g = /female/.test(u) ? 'female' : 'male';
      state.gender = g;
      let text='';
      try{ text = JSON.parse((opts&&opts.body)||'{}').text || ''; }catch(e){}
      const hit = window.__offlineAnswer(text);
      if(hit){
        return Promise.resolve(new Response(JSON.stringify(hit),
                                            {headers:{'Content-Type':'application/json'}}));
      }
      return onlineMT(text, g).then(body => new Response(JSON.stringify(body || {
        english:text, source:'offline',
        burmese:(g==='female'
          ? 'တစ်ဆိတ်လောက် ထပ်ပြောပေးပါ ရှင်။ နားမလည်သေးပါ။'
          : 'တစ်ဆိတ်လောက် ထပ်ပြောပေးပါ ခင်ဗျာ။ နားမလည်သေးပါ။'),
        hint:'ဘာသာပြန်မရပါ - အခြေခံအဖြေသာ ပေးနိုင်သည်', roman:'', literal:'',
        answers:[]}), {headers:{'Content-Type':'application/json'}}));
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
    if(hint) hint.textContent = '🎙 “တိုက်ရိုက်” ခလုတ်ကို နှိပ်ပြီး ဖုန်းကို စပီကာဖွင့်ကာ နားထောင်ပါ (Chrome + အင်တာနက် လိုသည်)';
    const mic = document.getElementById('mic');
    if(mic) mic.addEventListener('click', (e)=>{
      e.stopImmediatePropagation(); e.preventDefault();
      toast('🎙 တိုက်ရိုက် ခလုတ်ကို သုံးပါ');
    }, true);
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
