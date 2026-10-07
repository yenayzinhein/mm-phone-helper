#!/usr/bin/env python3
"""Render လမ်းညွှန်.md -> a single self-contained HTML file.

Same reason as build_standalone.py: the guide is meant to be opened on a phone
with no network, so the Padauk webfont has to be inlined or Burmese text falls
back to whatever (often broken) font the handset ships with.

Deliberately a tiny hand-rolled Markdown subset (headings, tables, fenced code,
lists, blockquotes, bold/inline-code, hr) -- pulling in a Markdown library for
one file is not worth it.

Usage:  python3 build_guide.py
"""

from __future__ import annotations

import base64
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "လမ်းညွှန်.md")
FONT = os.path.join(HERE, "app", "static", "fonts", "padauk-400.woff2")
FONT_B = os.path.join(HERE, "app", "static", "fonts", "padauk-700.woff2")
OUT = os.path.join(HERE, "dist", "လမ်းညွှန်.html")

CSS = """
:root{--bg:#14110c;--panel:#1d1913;--panel2:#262018;--line:#3a3125;
--gold:#e0b24a;--ink:#f4ead6;--muted:#b6a98f;--ok:#7dc98a;--bad:#d9715f;
--mm:'Padauk Web','Padauk','Myanmar Text','Noto Sans Myanmar','Myanmar3',sans-serif;}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1000px 500px at 50% -180px,#2a2115,transparent 70%),var(--bg);
color:var(--ink);font-family:var(--mm);font-size:17px;line-height:1.85;padding:0 0 80px}
.wrap{max-width:780px;margin:0 auto;padding:22px 18px}
h1{font-size:26px;line-height:1.4;margin:6px 0 4px;color:#fff}
h2{font-size:21px;color:var(--gold);margin:38px 0 10px;padding-bottom:8px;
border-bottom:1px solid var(--line);line-height:1.5}
h3{font-size:18px;color:#fff;margin:24px 0 6px;line-height:1.5}
p{margin:10px 0}
a{color:var(--gold)}
strong{color:#fff}
code{background:var(--panel2);border:1px solid var(--line);border-radius:6px;
padding:1px 6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88em}
pre{background:var(--panel);border:1px solid var(--line);border-radius:14px;
padding:14px;overflow-x:auto;line-height:1.7;margin:12px 0}
pre code{background:none;border:0;padding:0;font-size:14px;color:var(--muted)}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:15px;
background:var(--panel);border-radius:12px;overflow:hidden}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--panel2);color:var(--gold);font-weight:700}
tr:last-child td{border-bottom:0}
blockquote{margin:12px 0;padding:10px 14px;border-left:3px solid var(--gold);
background:var(--panel);border-radius:0 10px 10px 0;color:var(--muted)}
hr{border:0;border-top:1px solid var(--line);margin:28px 0}
ul,ol{padding-left:24px;margin:10px 0}
li{margin:5px 0}
.hero{background:linear-gradient(140deg,#2a2115,#1d1913);border:1px solid var(--line);
border-radius:18px;padding:18px;margin-bottom:8px}
.badge{display:inline-block;font-size:12px;background:var(--panel2);border:1px solid var(--line);
color:var(--gold);border-radius:999px;padding:2px 10px;margin-right:6px}
"""


def b64(path: str) -> str:
    with open(path, "rb") as fh:
        return "data:font/woff2;base64," + base64.b64encode(fh.read()).decode()


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def render(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # fenced code block
        if line.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(html.escape(lines[i], quote=False))
                i += 1
            i += 1
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>")
            continue

        # table
        if line.strip().startswith("|") and i + 1 < len(lines) \
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table><thead><tr>"]
            t += [f"<th>{inline(c)}</th>" for c in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        # headings
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            body = inline(m.group(2))
            if level == 1:
                out.append(f'<div class="hero"><h1>{body}</h1>'
                           f'<span class="badge">offline</span>'
                           f'<span class="badge">မြန်မာ</span></div>')
            else:
                out.append(f"<h{level}>{body}</h{level}>")
            i += 1
            continue

        if re.match(r"^---+\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        if line.startswith("> "):
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
            i += 1
            continue

        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            ordered = m.group(2)[0].isdigit()
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>")
            while i < len(lines):
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not mm:
                    break
                out.append(f"<li>{inline(mm.group(3))}</li>")
                i += 1
            out.append(f"</{tag}>")
            continue

        if line.strip():
            out.append(f"<p>{inline(line)}</p>")
        i += 1

    return "\n".join(out)


def main() -> str:
    md = open(SRC, encoding="utf-8").read()
    body = render(md)
    face = (
        "@font-face{font-family:'Padauk Web';src:url('%s') format('woff2');"
        "font-weight:400;font-display:swap;"
        "unicode-range:U+1000-109F,U+AA60-AA7F,U+200B-200D,U+25CC;}"
        "@font-face{font-family:'Padauk Web';src:url('%s') format('woff2');"
        "font-weight:700;font-display:swap;"
        "unicode-range:U+1000-109F,U+AA60-AA7F,U+200B-200D,U+25CC;}"
    ) % (b64(FONT), b64(FONT_B))

    doc = (
        "<!doctype html><html lang='my'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='theme-color' content='#14110c'>"
        "<title>ဖုန်းပြော အကူ — အသုံးပြုနည်း လမ်းညွှန်</title>"
        f"<style>{face}{CSS}</style></head><body><div class='wrap'>{body}"
        "</div></body></html>"
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return OUT


if __name__ == "__main__":
    p = main()
    print("built", p, f"({os.path.getsize(p)/1024:.0f} KB)")
