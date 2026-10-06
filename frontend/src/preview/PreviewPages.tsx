import { useState, type ReactNode } from 'react'
import {
  ArrowLeft, ArrowRight, BadgeCheck, BookmarkPlus, Check, ChevronLeft, ChevronRight, CircleHelp, Heart, Leaf,
  MapPin, ScanLine, SlidersHorizontal, Sparkles, ThumbsDown, ThumbsUp, UtensilsCrossed,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { discoveryMeals, preferenceGroups, visibleFoods } from './previewData'
import image1 from '../../../docs/Images/1.jpg'
import image2 from '../../../docs/Images/2.jpg'
import image3 from '../../../docs/Images/3.jpg'
import image4 from '../../../docs/Images/4.jpg'
import image5 from '../../../docs/Images/5.jpg'
import image6 from '../../../docs/Images/6.jpg'

type PageIntroProps = {
  eyebrow: string
  title: string
  children?: ReactNode
}

function PageIntro({ eyebrow, title, children }: PageIntroProps) {
  return (
    <header className="preview-page-intro">
      <div className="preview-page-intro__eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      {children && <p>{children}</p>}
    </header>
  )
}

function StepActions({ back, next, nextLabel }: { back?: string; next: string; nextLabel: string }) {
  return (
    <div className="preview-step-actions">
      {back ? <Link className="preview-button preview-button--quiet" to={back}><ArrowLeft aria-hidden="true" /> Back</Link> : <span />}
      <Link className="preview-button" to={next}>{nextLabel}<ArrowRight aria-hidden="true" /></Link>
    </div>
  )
}

export function PreviewScanPage() {
  return (
    <section className="preview-page preview-page--scan">
      <div className="preview-two-column">
        <PageIntro eyebrow="Meal analysis" title="Here’s what we found!" />
        <div className="scan-visual-card">
          <img className="preview-food-image preview-food-image--scan" src={image1} alt="Roasted squash, quinoa, greens, cabbage, and tomatoes in a bowl" />
          <div className="scan-visual-card__status"><ScanLine aria-hidden="true" /> Analysis complete</div>
        </div>
      </div>

      <section className="recognition-card" aria-labelledby="recognition-title">
        <div className="recognition-card__heading">
          <div>
            <span className="section-kicker">On your plate</span>
            <h2 id="recognition-title">Roasted vegetable grain bowl</h2>
          </div>
          <span className="soft-pill"><Leaf aria-hidden="true" /> In view</span>
        </div>
        <div className="food-label-grid">
          {visibleFoods.map((food) => (
            <div className="food-label" key={food.name}><Check aria-hidden="true" /><div><strong>{food.name}</strong><span>{food.detail}</span></div></div>
          ))}
        </div>
        <p className="uncertainty-note"><CircleHelp aria-hidden="true" /> Dressings and portions can be hard to read from a photo, so the details stay clear about what is less certain.</p>
      </section>
      <div className="scan-actions" aria-label="Meal actions">
        <button type="button" className="scan-action-button"><SlidersHorizontal aria-hidden="true" /><span>Improve accuracy</span></button>
        <Link to="/preview/preferences" className="scan-action-button scan-action-button--primary"><BookmarkPlus aria-hidden="true" /><span>Record meal</span></Link>
        <button type="button" className="scan-action-button scan-action-button--score"><BadgeCheck aria-hidden="true" /><span>Meal score</span></button>
      </div>
    </section>
  )
}

export function PreviewPreferencesPage() {
  const [selected, setSelected] = useState<string[]>(['Something cozy', 'Mostly plant-forward', 'Weeknight easy'])
  const [request, setRequest] = useState('')
  const toggle = (choice: string) => setSelected((current) => current.includes(choice) ? current.filter((item) => item !== choice) : [...current, choice])

  return (
    <section className="preview-page preview-page--preferences">
      <div className="preferences-header">
        <PageIntro eyebrow="Your preferences" title="What sounds good right now?">
          Start with a craving, a feeling, or whatever is on your mind.
        </PageIntro>
      </div>
      <section className="preference-panel" aria-label="Food preferences preview">
        <label className="meal-request-field" htmlFor="meal-request">
          <span>I’m looking for…</span>
          <textarea
            id="meal-request"
            value={request}
            onChange={(event) => setRequest(event.target.value)}
            placeholder="Something warm, savory, and easy after a long day."
            rows={6}
          />
          <small>{request.length > 0 ? `${request.length}/180` : 'Try a craving, mood, ingredient, or occasion.'}</small>
        </label>
        {preferenceGroups.map((group) => (
          <fieldset className="preference-group" key={group.title}>
            <legend>{group.title}</legend>
            <div className="choice-chip-row">
              {group.choices.map((choice) => {
                const isSelected = selected.includes(choice)
                return <button type="button" key={choice} aria-pressed={isSelected} onClick={() => toggle(choice)} className={`choice-chip${isSelected ? ' is-selected' : ''}`}>{isSelected && <Check aria-hidden="true" />}{choice}</button>
              })}
            </div>
          </fieldset>
        ))}
      </section>
      <StepActions back="/preview/scan" next="/preview/discover" nextLabel="See what fits" />
    </section>
  )
}

export function PreviewDiscoverPage() {
  const moods = ['Something cozy', 'Fresh & bright', 'A little spicy', 'Easy comfort']
  const [mood, setMood] = useState(moods[0])
  const [activeSlide, setActiveSlide] = useState(0)
  const moveMood = (direction: 1 | -1) => {
    const currentIndex = moods.indexOf(mood)
    setMood(moods[(currentIndex + direction + moods.length) % moods.length])
    setActiveSlide((current) => (current + direction + 6) % 6)
  }

  return (
    <section className="preview-page preview-page--discover">
      <PageIntro eyebrow="Find your next meal" title="What are you in the mood for?">
        Pick a feeling to narrow it down.
      </PageIntro>
      <div className="mood-picker" aria-label="Choose a meal mood">
        {moods.map((item) => <button type="button" key={item} onClick={() => setMood(item)} aria-pressed={mood === item} className={`mood-pill${mood === item ? ' is-selected' : ''}`}>{item}</button>)}
      </div>
      <section className="discovery-section" aria-labelledby="discover-results">
        <div className="discovery-section__heading"><div><span className="section-kicker">Made for {mood.toLowerCase()}</span><h2 id="discover-results">Pick a direction</h2></div></div>
        <div className="discovery-carousel">
          <button type="button" className="carousel-arrow" onClick={() => moveMood(-1)} aria-label="Show previous meal ideas"><ChevronLeft aria-hidden="true" /></button>
          <div className="meal-card-grid">
            {discoveryMeals.map((meal, index) => (
              <Link className="meal-card" to="/preview/recommendation" key={meal.name}>
                <img className="meal-card__image" src={[image2, image3, image4][index]} alt={[
                  'Mushroom noodle bowl with bok choy',
                  'Herby lentil bowl with cucumber and peppers',
                  'Roasted tomato and white bean bowl with arugula',
                ][index]} />
                <div className="meal-card__body"><span>{meal.match}</span><h3>{meal.name}</h3><p>{meal.description}</p><span className="meal-card__link">See why it fits <ChevronRight aria-hidden="true" /></span></div>
              </Link>
            ))}
          </div>
          <button type="button" className="carousel-arrow" onClick={() => moveMood(1)} aria-label="Show more meal ideas"><ChevronRight aria-hidden="true" /></button>
          <div className="carousel-dots" aria-label="Meal idea pages">{Array.from({ length: 6 }, (_, index) => <button type="button" key={index} onClick={() => setActiveSlide(index)} aria-label={`Show meal idea page ${index + 1}`} aria-current={activeSlide === index ? 'true' : undefined} className={activeSlide === index ? 'is-active' : ''} />)}</div>
        </div>
      </section>
      <StepActions back="/preview/preferences" next="/preview/recommendation" nextLabel="See a match" />
    </section>
  )
}

export function PreviewRecommendationPage() {
  return (
    <section className="preview-page preview-page--recommendation">
      <div className="recommendation-hero">
        <img className="preview-food-image preview-food-image--recommendation" src={image2} alt="Mushroom noodles with bok choy and sesame" />
        <div className="recommendation-hero__copy">
          <span className="section-kicker">A match for your current craving</span>
          <h1>Miso mushroom noodles</h1>
          <p>Silky noodles, roasted mushrooms, and greens in a deeply savory broth.</p>
          <div className="recommendation-actions"><button type="button" className="save-button"><Heart aria-hidden="true" /> Save this idea</button><button type="button" className="recipe-button">View recipe</button><Link to="/preview/swaps" className="recipe-button">Swap meal</Link></div>
        </div>
      </div>
      <div className="recommendation-grid">
        <section className="why-card"><span className="section-kicker">Why this fits</span><h2>Warm, savory, and easy to make your own.</h2><p>It matches the cozy feeling you picked and can flex around a plant-forward dinner.</p></section>
        <section className="ingredient-card"><span className="section-kicker">In this bowl</span><div className="ingredient-chips"><span>Mushrooms</span><span>Noodles</span><span>Bok choy</span><span>Miso broth</span><span>Sesame</span></div><p>Earthy, savory, and just a little nutty.</p></section>
      </div>
      <section className="next-idea-card"><UtensilsCrossed aria-hidden="true" /><div><span className="section-kicker">Another direction</span><h2>Want something you can pick up instead?</h2><p>See a nearby option with a similar feel.</p></div><MapPin aria-hidden="true" /></section>
      <StepActions back="/preview/discover" next="/preview/swaps" nextLabel="Explore a swap" />
    </section>
  )
}

export function PreviewSwapsPage() {
  const swapOptions = [
    { value: 'tofu', title: 'Soba with tofu & greens', description: 'Still savory and cozy, with a little more protein.' },
    { value: 'crisp', title: 'Crispy tofu & sesame soba', description: 'More crunch, with the same warm noodle base.' },
    { value: 'greens', title: 'Extra greens & tofu', description: 'A brighter, more vegetable-forward version.' },
  ]
  const [swapOption, setSwapOption] = useState(swapOptions[0].value)
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null)
  const selectedSwap = swapOptions.find((option) => option.value === swapOption) ?? swapOptions[0]

  return (
    <section className="preview-page preview-page--swaps">
      <header className="swap-toolbar"><div><span className="section-kicker">Swap options</span><h1>Change one thing</h1></div><label>Change swap option<select value={swapOption} onChange={(event) => setSwapOption(event.target.value)}>{swapOptions.map((option) => <option key={option.value} value={option.value}>{option.title}</option>)}</select></label></header>
      <section className="swap-stage" aria-label="Meal swap preview">
        <div className="swap-meal-card"><img className="swap-meal-card__image" src={image2} alt="Mushroom noodles with bok choy" /><div><span className="section-kicker">Your starting point</span><h2>Miso mushroom noodles</h2><p>Rich, warm, and savory.</p></div></div>
        <div className="swap-meal-card swap-meal-card--accent is-active"><img className="swap-meal-card__image" src={image5} alt="Soba noodles with crispy tofu and greens" /><div><span className="section-kicker">Try this instead</span><h2>{selectedSwap.title}</h2><p>{selectedSwap.description}</p></div></div>
      </section>
      <div className="swap-feedback"><span>Does this swap work for you?</span><div><button type="button" className={feedback === 'up' ? 'is-selected' : ''} aria-pressed={feedback === 'up'} onClick={() => setFeedback('up')}><ThumbsUp aria-hidden="true" /> Yes</button><button type="button" className={feedback === 'down' ? 'is-selected' : ''} aria-pressed={feedback === 'down'} onClick={() => setFeedback('down')}><ThumbsDown aria-hidden="true" /> Not quite</button></div></div>
      <StepActions back="/preview/recommendation" next="/preview/remember" nextLabel="Save swap" />
    </section>
  )
}

export function PreviewRememberPage() {
  return (
    <section className="preview-page preview-page--remember">
      <header className="taste-replay-header"><div><span className="section-kicker">Taste replay</span><h1>Bring back a meal you loved.</h1></div><button type="button"><Heart aria-hidden="true" /> Saved</button></header>
      <section className="taste-replay-card">
        <img src={image6} alt="Crispy tofu rice bowl with greens and lime" />
        <div className="taste-replay-card__details"><span className="section-kicker">Your Tuesday favorite</span><h2>Crispy tofu rice bowl</h2><p>Sesame-glazed tofu, tender greens, jasmine rice, and lime.</p><div className="flavor-tags"><span>Crunchy</span><span>Savory</span><span>Bright</span><span>Weeknight-easy</span></div><div className="taste-replay-card__actions"><button type="button" className="preview-button">Make it again <ArrowRight aria-hidden="true" /></button><button type="button" className="recipe-button">Try a remix</button></div></div>
      </section>
      <section className="taste-note"><Sparkles aria-hidden="true" /><div><span className="section-kicker">What made it hit</span><p>The sesame-lime finish and crisp tofu are the parts worth repeating.</p></div><button type="button">Edit notes</button></section>
    </section>
  )
}
