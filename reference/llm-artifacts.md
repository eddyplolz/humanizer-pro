# LLM Artifact & Placeholder Detection

Mechanical tells: tokens and stubs that leak when an AI chat reply is pasted as finished content.
Unlike prose tells, these are **deterministic** — if present, the text is AI-generated with near
certainty. Detect them with a literal sweep (regex), remove them, and **resolve the underlying thing**
they replaced (a real citation, a real link, a filled-in value). Deleting the token without restoring
the reference can hide a fabricated-source problem — always check what the token stood in for.

Source: Wikipedia "Signs of AI writing" §Markup, §Phrasal templates (real on-wiki examples).

## One-pass sweep (ripgrep)

Run this union regex over any drafted/pasted text before delivering it:

```
rg -nP "cite​?turn\d+\w+|turn\d+(search|image|news|file)\d+|contentReference|oaicite|oai_citation|attributableIndex|grok[_-](card|render)|grok-card|\[attached_file:\d+\]|\[web:\d+\]|【\d+†|utm_source=chatgpt\.com|\bINSERT_[A-Z_]+\b|PASTE_[A-Z_]+_HERE|20\d{2}-XX-XX|\[(Your Name|Entertainer's Name|insert|describe)[^\]]*\]"
```

(The PUA characters around `turnN` are invisible; matching `turn\d+search\d+` etc. catches them anyway.)

## Catalog

### 1. ChatGPT web-search citation stubs
- **Looks like:** `citeturn0search0`, `turn0search1`, `iturn0image0turn0image1`, `citeturn0news0`,
  `citeturn1file0`, `cite<generated-reference-identifier>`. Number after `search`/`image` increments
  through the text. Often wrapped in invisible Private-Use-Area Unicode.
- **Regex:** `(?:cite)?turn\d+(?:search|image|news|file)\d+`
- **Fix:** Delete. Replace with a real citation/link only if the claim is actually supported; otherwise
  the claim may be unsourced or hallucinated — flag it.

### 2. ChatGPT reference-markup bug (`contentReference` / `oaicite`)
- **Looks like:** `:contentReference[oaicite:16]{index=16}`, `oai_citation`, `[oai_citation:0‡domain.com](https://…)`, `Example+1` (a `+N` suffix where a link should be).
- **Regex:** `:?contentReference\[oaicite:\d+\]\{index=\d+\}|oai_citation(?::\d+)?|\b\w+\+\d+\b(?=\s|$)`
- **Fix:** Delete the stub; restore the intended reference if the fact needs one.

### 3. JSON attribution blocks
- **Looks like:** `^[Sentence text.]({"attribution":{"attributableIndex":"1009-1"}})` — the real
  sentence wrapped in `^[ ]( … )` with trailing JSON; indices increment.
- **Regex:** `\(\{"attribution":\{"attributableIndex":"\d+-\d+"\}\}\)|\^\[[^\]]+\]\(`
- **Fix:** Keep the bracketed sentence, delete the `^[`, the closing `]`, and the JSON.

### 4. Perplexity tags
- **Looks like:** `[attached_file:1]`, `[web:1]` at sentence ends.
- **Regex:** `\[(?:attached_file|web):\d+\]`
- **Fix:** Delete; restore a real citation if needed.

### 5. Grok citation cards
- **Looks like:** `grok_card`, `<grok-card data-id="e8ff4f" data-type="citation_card">`,
  `[](grok_render_citation_card_json={"cardIds":["3bb883"]})`.
- **Regex:** `grok[_-]card|<grok-card[^>]*>|grok_render_citation_card_json=\{[^}]*\}`
- **Fix:** Delete the whole tag; restore a real source if the claim needs one.

### 6. Lenticular-bracket / dagger references
- **Looks like:** `【85†L261-269】`, `【854140639155648†L119-L123】` (a citation/line-range pointer).
- **Regex:** `【\d+†[^】]*】`
- **Fix:** Delete; replace with a proper citation if the statement requires support.

### 7. Tracking parameters in URLs
- **Looks like:** `https://site.com/page?utm_source=chatgpt.com`, `&utm_source=chatgpt.com`.
- **Regex:** `[?&]utm_source=chatgpt\.com`
- **Fix:** Strip the `utm_source` (and any sibling `utm_*`) query params from the URL. A
  `utm_source=chatgpt.com` is a direct fingerprint that the link came from a ChatGPT session.

### 8. Unfilled phrasal-template placeholders
- **Looks like:** `[Your Name]`, `[Entertainer's Name]`, `[Describe the specific section…]`,
  `[insert date]`, `INSERT_SOURCE_URL_30`, `PASTE_YOUTUBE_VIDEO_URL_HERE`, `SOURCE_PUBLISHER`,
  `<!-- Add if available with citation -->`.
- **Regex:** `\[(?:Your Name|Entertainer's Name|insert[^\]]*|describe[^\]]*|link to[^\]]*)\]|\bINSERT_[A-Z0-9_]+\b|PASTE_[A-Z0-9_]+_HERE|\bSOURCE_[A-Z_]+\b|<!--\s*Add (?:if available|[^>]*)-->`
- **Fix:** The author forgot to fill the blank. Supply the real value, or remove the sentence if the
  value is unknown — never ship the bracketed stub.

### 9. Placeholder dates
- **Looks like:** `2025-XX-XX`, `2022-11-XX`, `access-date=2025-XX-XX`, `20XX`.
- **Regex:** `20\d{2}-(?:XX|\d{2})-XX|\b20XX\b`
- **Fix:** Replace with the actual date, or drop the field. (Note: a literal `{{as of}}`-style date is
  fine; only the `XX` stub is the tell.)

## Why "delete only" is not enough
Every artifact above sits where a **real reference or value** belonged. The model emitted the stub
because it was citing (or pretending to cite) a source. Removing the stub silently can leave an
unsupported or fabricated claim looking clean. For each hit: remove the token **and** decide whether
the surrounding statement needs a genuine source — if it does and you can't find one, flag the claim
rather than laundering it.
