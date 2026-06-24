# Wiki and Article Mode

Use this reference when the request mentions wiki, Wikipedia, MicrasWiki, encyclopedic article,
neutral tone, wikitext, citations, source-bound writing, or article draft.

Wiki/article mode is not a "make it sound human" voice pass. It is a neutralization and sourcing pass.
The output should read like a careful article, not a casual essay.

## Goals

- Remove promotional tone, unsupported significance, and brochure language.
- Preserve factual claims, dates, names, citations, and markup unless they are clearly wrong.
- Flag unsupported claims instead of inventing sources.
- Convert Markdown artifacts to the requested target format when needed.
- Keep prose neutral, concrete, and proportionate.

## Remove or Recast

- **Promotional adjectives:** renowned, vibrant, beloved, world-class, must-see, groundbreaking.
- **Unsupported significance:** "played a pivotal role," "left an enduring legacy," "marked a turning
  point," "became an important symbol" without a source that actually supports that claim.
- **Vague attribution:** "observers note," "critics say," "widely regarded," "some believe" without a
  named source.
- **Superficial analysis:** trailing "highlighting," "underscoring," "showcasing," or "reflecting
  broader trends" when no concrete relationship is shown.
- **Padding sections:** legacy/impact/future paragraphs that repeat notability rather than adding
  sourced content.
- **Synthetic voice:** first person, jokes, conversational openers, rhetorical questions, and casual
  intimacy.

## Source Discipline

- Keep existing citations attached to the claims they support.
- If an artifact token appears where a citation belonged, remove the token and flag the claim as
  source-risky.
- If a claim needs support and none is present, write a source-risk note instead of making the prose
  sound more confident.
- Do not turn a weak source into a stronger claim. If the source says "opened in 1998," do not write
  "became a landmark in 1998."
- Do not add invented access dates, publishers, quotations, page numbers, or citation templates.

## Wikitext and Markup

- Convert Markdown headings to target headings if asked for wikitext (`##` -> `== Heading ==`).
- Convert Markdown links to target links when the target is known (`[text](url)` -> `[url text]` for
  external links, or `[[Article|text]]` only when the article title is known).
- Remove Markdown bold used as inline list labels unless the target article convention requires it.
- Preserve templates, categories, infobox fields, and existing citation syntax unless the user asks
  for a conversion.
- If markup intent is unclear, flag it rather than guessing.

## Article Workflow

1. Run `reference/llm-artifacts.md` first.
2. Identify the target: plain article prose, Markdown, wikitext, or another house format.
3. Separate supported facts from unsupported claims.
4. Neutralize promotional and significance language.
5. Rebuild paragraphs around concrete facts in chronological or logical order.
6. Check for target-markup leakage.
7. Return neutral text plus source-risk notes.

## Output

For normal article edits, return:

1. Neutral rewrite in the target format.
2. Source-risk notes for claims that lost fake citations, lack support, or need verification.

Do not include personality notes, jokes, or "human voice" suggestions in wiki/article mode.
