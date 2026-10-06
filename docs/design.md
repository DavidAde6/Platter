# Platter — Launch Design Template

> An editable design brief and landing-page outline for Platter's showcase
> period. Replace text in `{{double braces}}`, and replace asset paths once
> final media is available. This document intentionally separates what people
> can use now from the product vision.

## At a glance


| Item                   | Working direction                                                       |
| ---------------------- | ----------------------------------------------------------------------- |
| Audience               | Food-positive explorers who want helpful food context without judgment. |
| Brand promise          | **Eat what you want. Know enough to not worry.**                        |
| Supporting idea        | **See what's on your plate. Find what fits next.**                      |
| Public action          | Join the waitlist — no account or app access is created.                |
| Private preview target | January 1, 2027                                                         |
| Hard launch target     | April 2027                                                              |


---



## 1. Brand system



### Voice

Platter should sound calm, warm, curious, and specific about food. It is a
meal companion, not a tracker, coach, or health authority.

**Use:** meal, taste, plate, ingredient, choice, context, fits, curious,
perhaps, likely, and range.

**Avoid:** calories as a moral score, health grades, streaks, perfect days,
cheat meals, medical claims, productivity language, or internal technical
terms.

### Color tokens


| Name     | Hex       | Suggested role                         |
| -------- | --------- | -------------------------------------- |
| Cream    | `#FAF7F1` | Main page background                   |
| Ink      | `#1F1B17` | Primary text and dark surfaces         |
| Paprika  | `#C8563C` | Primary action and key emphasis        |
| Olive    | `#526747` | Secondary accent and calm confirmation |
| Oat      | `#E7D6BF` | Card, border, and supporting surfaces  |
| Marigold | `#E9AE36` | Small editorial highlight              |




### Typography


| Role      | Typeface | Guidance                                                         |
| --------- | -------- | ---------------------------------------------------------------- |
| Display   | Fraunces | Use for headlines, pull quotes, and editorial moments only.      |
| Body / UI | DM Sans  | Use for navigation, labels, forms, and readable supporting text. |




### Art direction

- Favor beautifully lit, candid meals: varied cuisines, settings, budgets, and textures.
- Let food lead the frame; avoid generic wellness imagery, body ideals, and sterile green interfaces.
- Keep interface cards tactile, spacious, and quietly layered.
- Do not put essential or unreadable copy inside an image.

---



## 2. Asset map

Use these paths as a handoff convention. Each final asset needs a source,
license, crop guidance, and alt-text decision.


| ID                   | Placement         | Placeholder                              | Final asset notes                                                          | Alt text / caption                                       |
| -------------------- | ----------------- | ---------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------- |
| `hero-meal`          | Hero              | `{{/public/images/hero-meal.jpg}}`       | Wide, candid meal image; preserve room for text.                           | `{{Describe the visible meal; omit decorative assets.}}` |
| `hero-device`        | Hero              | `{{/public/images/hero-device.png}}`     | Optional phone mockup; show a concept preview badge.                       | `{{Phone showing a fictional Platter concept screen.}}`  |
| `step-see`           | Story: See        | `{{/public/images/step-see.jpg}}`        | Plate captured in everyday light.                                          | `{{...}}`                                                |
| `step-understand`    | Story: Understand | `{{/public/images/step-understand.png}}` | Fictional ingredient/context screen.                                       | `{{...}}`                                                |
| `step-choose`        | Story: Choose     | `{{/public/images/step-choose.png}}`     | Fictional cook-and-go choices.                                             | `{{...}}`                                                |
| `vision-film-poster` | Vision media      | `{{/public/video/vision-poster.jpg}}`    | Mobile-safe poster for the 55–60 sec silent film.                          | `{{A preview of Platter's future meal journey.}}`        |
| `vision-film`        | Vision media      | `{{/public/video/platter-vision.webm}}`  | Provide matching MP4, transcript, visible controls, and no autoplay audio. | Transcript required.                                     |
| `see-loop`           | Vision gallery    | `{{/public/video/see-loop.webm}}`        | Muted looping concept clip or static fallback.                             | `{{...}}`                                                |
| `choose-loop`        | Vision gallery    | `{{/public/video/choose-loop.webm}}`     | Muted looping concept clip or static fallback.                             | `{{...}}`                                                |
| `remember-loop`      | Vision gallery    | `{{/public/video/remember-loop.webm}}`   | Muted looping concept clip or static fallback.                             | `{{...}}`                                                |


> **Asset rule:** never use a private upload in marketing. All product screens,
> people, meal history, locations, reviews, and metrics shown here are clearly
> fictional unless proven otherwise.

---



## 3. Proposed landing page



### Desktop structure

```text
┌──────────────────────────────────────────────────────────────────────┐
│ PLATTER     How it works   The vision   Private preview   [Waitlist] │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│ Eat what you want.                                                   │
│ Know enough to not worry.              [ HERO FOOD PHOTO / DEVICE ] │
│ A meal companion for clearer food       {{hero-meal}}                │
│ context and more satisfying choices.                                 │
│ [Join the waitlist]  Private preview: Nov 2026                       │
│                       Public launch target: Jan 1, 2027              │
├──────────────────────────────────────────────────────────────────────┤
│ SEE A PLATE → UNDERSTAND IT HONESTLY → FIND WHAT FITS NEXT          │
│ [step-see]             [step-understand]          [step-choose]     │
├──────────────────────────────────────────────────────────────────────┤
│ THE PRODUCT VISION                              [CONCEPT PREVIEW]   │
│ [ 55–60 second vision film / poster ]                               │
├──────────────────────────────────────────────────────────────────────┤
│ See                 Choose                    Remember               │
│ [loop/screen]       [loop/screen]             [loop/screen]         │
├──────────────────────────────────────────────────────────────────────┤
│ Taste first. Honest about uncertainty. Never judgmental.             │
├──────────────────────────────────────────────────────────────────────┤
│ Private preview targets November 2026. Hard launch: January 1, 2027 │
│ [email________________________] [Join the waitlist]                  │
│ By joining, you are asking for updates—not creating an account.      │
├──────────────────────────────────────────────────────────────────────┤
│ PLATTER / Privacy / Contact / © {{year}}                             │
└──────────────────────────────────────────────────────────────────────┘
```



### Mobile behavior

- Keep the promise, launch dates, and waitlist action visible in the first viewport.
- Collapse navigation into a labelled menu while retaining a visible **Join the waitlist** button.
- Stack every visual/text pair; never rely on horizontal scrolling.
- Use a poster image if motion is disabled, unavailable, or too costly to load.

---



## 4. Section-by-section content template



### Header


| Element           | Draft / placeholder                         |
| ----------------- | ------------------------------------------- |
| Wordmark          | `PLATTER` + quiet plate/portion mark        |
| Links             | How it works · The vision · Private preview |
| Persistent action | **Join the waitlist**                       |




### Hero

```md
Eyebrow: {{A meal companion for curious eaters}}
Headline: Eat what you want. Know enough to not worry.
Body: See what's on your plate, understand it without false certainty,
and find what fits next.
Primary CTA: Join the waitlist
Availability: Private preview targets November 2026. Hard launch targets January 1, 2027.
Visual: {{hero-meal}} / {{hero-device}}
```



### How it works


| Step | Headline                  | Body template                                                     | Graphic               |
| ---- | ------------------------- | ----------------------------------------------------------------- | --------------------- |
| 01   | See what’s on your plate. | `{{Capture a meal and start with the foods you can see.}}`        | `{{step-see}}`        |
| 02   | Understand it honestly.   | `{{Context that names what is clear—and what is less certain.}}`  | `{{step-understand}}` |
| 03   | Find what fits next.      | `{{A helpful next choice based on taste, mood, and the moment.}}` | `{{step-choose}}`     |




### Vision preview

Every screen in this section must display a persistent **Concept preview** label.

```md
Section label: The product vision
Headline: A little more clarity. A more satisfying next choice.
Body: {{Introduce the intended experience without suggesting it is available today.}}
Media: {{vision-film-poster}} + {{vision-film}}
Transcript link: {{/vision-transcript}}
```



#### Concept-screen captions


| Moment             | Safe caption                                        |
| ------------------ | --------------------------------------------------- |
| Discover           | Start with what sounds good.                        |
| Scan               | Visible foods, named with care.                     |
| Processing         | Looking closely at your meal…                       |
| Meal understanding | A useful range, with context—not false precision.   |
| Why this fits      | `{{One plain-language taste or occasion reason.}}`  |
| Cook and Go        | A recipe and a nearby idea—both part of the vision. |
| Remember           | A quiet memory of what you enjoyed.                 |




### Principles

```md
Headline: Food is more than a score.
Principle 1: Taste comes first.
Principle 2: Useful information can be uncertain.
Principle 3: No streaks, rankings, or shame required.
```



### Availability and waitlist

```md
Headline: We’re making Platter with care.
Availability: Private preview targets November 2026. Hard launch targets January 1, 2027.
Field label: Email address
Consent: {{Required consent language and link to privacy policy.}}
Clarifier: Joining the waitlist does not create an account or grant app access.
Success state: You’re on the list. We’ll write when there’s something real to share.
Error state: {{Use plain, specific input guidance.}}
```

---



## 5. Concept-screen data guardrails

Use fictional sample data and never show precision that the product cannot
support. Nutrition examples, when introduced in a future concept, must show a
range and explain the uncertainty in familiar language.

```text
CONCEPT PREVIEW
Roasted vegetable grain bowl
Likely includes: squash, greens, grains, tahini dressing
Energy: roughly {{range}} for this portion
Why a range? Portions and preparation can change the answer.
```

Do not imply the live product currently provides discovery, nutrition ranges,
recipes, nearby suggestions, or a complete preference model.

---



## 6. Interaction and accessibility checklist

- [ ] The hero communicates the promise, availability, and next action without scrolling.
- [ ] All actions are keyboard reachable with a visible focus state.
- [ ] Input labels, consent, validation, and error messages are explicit.
- [ ] Color is never the only way information is conveyed; contrast is sufficient.
- [ ] Images have considered alt text; decorative images use empty alt text.
- [ ] Motion respects `prefers-reduced-motion`, pauses or has controls, and has static fallbacks.
- [ ] Video provides a poster, MP4/WebM versions, transcript, captions when needed, and no autoplay audio.
- [ ] The experience works on small screens, slow connections, and without JavaScript-created media.
- [ ] “Concept preview” remains present on all future-product material.
- [ ] The waitlist is email-only, consented, and clearly separate from product accounts.

---



## 7. Design review prompts

Before publishing, test this page with five audience-matched people. They
should be able to answer, unprompted:

1. What is Platter?
2. What is available today, and what is only a concept?
3. When might they be able to try it?
4. What happens after joining the waitlist?
5. Does Platter feel helpful about food rather than pressuring?



### Change log


| Date           | Owner    | Change                         | Status |
| -------------- | -------- | ------------------------------ | ------ |
| {{YYYY-MM-DD}} | {{name}} | Initial launch design template | Draft  |


