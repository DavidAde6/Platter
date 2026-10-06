# Platter Launch Experience Blueprint

> A decision guide for showing Platter before the product is complete. This is
> not a release checklist and it is not product copy. It records the questions,
> references, and quality bar that future design, media, and launch work must
> satisfy.

## The point of the public experience

Platter is for **food-positive explorers**: people who care about how they
feel and what they eat, but do not want a clinical tracker or a lecture.

The public experience has one job: make a visitor understand that Platter can
help them see a meal, understand it without false certainty, and choose what
fits next. It must also make an equally clear distinction between the product
vision and the functionality that exists today.

### Message hierarchy

| Level | Locked language | What it protects |
| --- | --- | --- |
| Brand promise | **Eat what you want. Know enough to not worry.** | A calm, non-punitive point of view. |
| Supporting idea | **See what's on your plate. Find what fits next.** | The Scan-to-Discover product story. |
| First-time explanation | A meal companion for clearer food context and more satisfying next choices. | Comprehension without an AI or nutrition lecture. |
| Availability | Private preview targets November 2026. Hard launch targets January 1, 2027. | Honesty about access and timing. |

Avoid calorie-policing, health grades, streaks, perfect days, cheat meals,
medical claims, and productivity language. Use familiar food language rather
than internal terms such as model, confidence schema, artifacts, or ranking.

## Brand quality bar

### Visual character

Platter is **warm editorial food culture**, not generic green wellness
software. A visitor should think “someone understands a good dinner” before
they think “nutrition app.”

| Element | Direction | Questions to use when reviewing work |
| --- | --- | --- |
| Color | Cream `#FAF7F1`, ink `#1F1B17`, paprika `#C8563C`, olive `#526747`, oat `#E7D6BF`, marigold `#E9AE36`. | Is color providing hierarchy and warmth, rather than implying good/bad food? |
| Type | Fraunces for expressive display moments; DM Sans for reading and UI. | Is the editorial voice reserved for meaning, while interaction remains effortless to scan? |
| Mark | Wordmark-first with a quiet plate/portion mark. | Can the mark sit beside food photography without competing with it? Does it avoid the stock wellness-symbol feel? |
| Photography | Beautifully lit, candid real meals across cuisines, textures, budgets, and contexts. | Does the image feel appetizing and specific? Does the set avoid presenting one cuisine or body ideal as the default? |
| Interface | Generous space, tactile cards, restrained depth, clear labels. | Can a first-time visitor tell what is live, what is a concept, and what action is available? |

Every public photograph needs a source, license, crop notes, alt text decision,
and whether it depicts a real or fictional meal. Do not use a person’s private
upload in marketing. Do not place unreadable text inside generated imagery.

### Reference research

Build a moodboard from food-editorial, boutique-hospitality, and calm
productivity references. Study only these properties:

- information hierarchy: what earns first attention, and what stays quiet;
- emotional temperature: intimate, generous, curious, not clinical;
- typography: contrast, scale, rhythm, and readability;
- accessibility: contrast, focus, labels, alternatives to motion;
- motion: pacing, pause points, and what remains understandable when paused.

Do not reproduce another product's copy, screen layout, logos, icons, or
photography. Review candidate references against warmth, legibility, cultural
breadth, and originality before they influence the system.

Useful anchors:

- [NN/G's usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/)
  for clarity, feedback, familiar language, and recovery from errors.
- [W3C's image alternative-text decision tree](https://www.w3.org/WAI/tutorials/images/decision-tree/)
  for marketing photographs, concept screens, and posters.
- [W3C's caption guidance](https://www.w3.org/WAI/media/av/captions/) for
  video transcripts, captions, and human review of automatic captions.

## Public landing experience

The public domain is a showcase until hard launch. It is not a disguised beta
or a funnel into unfinished uploads.

| Surface | Visitor should understand | Required signal |
| --- | --- | --- |
| Header | Platter, how it works, the vision, and private preview are the only navigation concepts. | Persistent **Join the waitlist** action. |
| Hero | Platter is a meal companion; the promise is emotional before technical. | Food-led visual and the two launch targets. |
| Three-part story | Scan a plate → Understand it honestly → Find what fits next. | One short benefit per step; no implementation jargon. |
| Vision gallery | The full product includes Scan, discovery, and remembered taste. | Persistent **Concept preview** treatment and fictional sample data. |
| Principles | Platter values taste, honest uncertainty, and no judgment. | Explicit contrast with streaks, rankings, and shame. |
| Availability | The product is still being made, and access is not public. | November 2026 / January 1, 2027 targets. |
| Waitlist | Joining does not make an account or grant app access. | Email-only form, required consent, concise privacy copy, neutral success state. |

The page should remain useful with reduced motion, without JavaScript-created
media, at mobile width, and when the visitor never scrolls beyond the hero.

## Product vision preview

### What the preview is allowed to show

The preview represents the intended completed experience. It may show:

1. **Discover** — a simple, taste-led starting point for “what do I want?”
2. **Scan** — a photo becomes visible-food labels.
3. **Processing** — visible system status and calm language while analysis runs.
4. **Meal understanding** — ingredient and preparation context; future
   nutrition presented as an honest range with visible uncertainty.
5. **Why this fits** — a one-line reason for a cook or nearby suggestion.
6. **Cook and Go cards** — a recipe option and a local option, each clearly
   framed as product vision until available.
7. **Log and preferences** — quiet memory that makes later suggestions more
   personal without turning into a scorecard.
8. **Private preview and waitlist** — access boundaries that feel considerate,
   not exclusionary.

### What the preview must never imply

- The present app has nutrition ranges, discovery, recipes, nearby suggestions,
  or a full preference model.
- A food photo produces a clinically reliable answer.
- Any fictional person, food history, location, review, or metric is real.
- Users are ranked, judged, guaranteed a health outcome, or given medical advice.

Every future-only screen carries an unobtrusive but persistent **Concept
preview** label. Every nutrition example uses a range and a plain-language
uncertainty cue. Fictional content should be culturally varied, plausible, and
free from artificial social proof.

## Vision media brief

The flagship asset is a 55–60 second silent motion mockup. It is a product
vision film, not a screen recording of the live app.

| Time | Moment | Feeling the frame must leave |
| --- | --- | --- |
| 0–6s | A satisfying meal is captured. | This begins with real food, not restriction. |
| 6–17s | Visible foods appear; one ambiguous element is named as uncertain. | Platter is thoughtful, not overconfident. |
| 17–28s | The meal becomes a simple understanding card with a range. | Information can be useful without pretending to be exact. |
| 28–40s | The user asks for a vibe; cook and nearby options appear with a why line. | The product helps with the next decision, not just the last meal. |
| 40–51s | A quiet log and preference cue make tomorrow feel easier. | The system remembers taste without turning life into a dashboard. |
| 51–60s | Brand promise, preview target, launch target, and waitlist. | A clear invitation without false urgency. |

Support the film with three muted looping clips: **See** (scan), **Choose**
(recommendation), and **Remember** (log). The site can use CSS motion and
concept screens before the final films exist, but must not label them videos.

Final media should ship as a mobile-safe poster plus MP4 and WebM derivatives.
Provide a transcript; provide reviewed captions whenever audio conveys meaning;
respect `prefers-reduced-motion`; never autoplay audio; keep controls visible;
and test the story at small widths before final export.

## Access and trust boundary

During showcase mode, only invited testers may enter the incomplete app.

| Audience | Entry | Data boundary |
| --- | --- | --- |
| Public visitor | Landing page and waitlist only. | No account, upload, meal, or analysis endpoint access. |
| Waitlisted visitor | Same public experience until invited. | Waitlist email is separate from `users`. |
| Invited tester | Private preview sign-in using an allowlisted, manually provisioned account. | Server verifies the allowlist before protected APIs run. |
| Team operator | Manages the environment allowlist and exports consented waitlist records. | No public admin controls. |

The access rule belongs in the backend as well as routing. A determined visitor
must not be able to use an API just by discovering a client-side URL. Revisit
this policy before hard launch; it is intentionally temporary.

## Questions that indicate readiness

The launch surface is ready to represent Platter when five audience-matched
people can answer all of these without prompting:

- What is Platter, in one sentence?
- What could I use today versus what is a vision preview?
- When could I expect to try it?
- What happens after I join the waitlist?
- Does the experience feel like help with food, rather than pressure about food?

Also review keyboard navigation, visible focus, input errors, contrast,
small-screen hierarchy, slow connections, media-disabled behavior, consent
capture, anonymous routes, waitlisted routes, allowlisted routes, and the
protected upload API. A polished visual is not ready if it obscures any of
those answers.
