export type PreviewStep = {
  path: string
  shortLabel: string
  label: string
}

export const previewSteps: PreviewStep[] = [
  { path: '/preview/scan', shortLabel: 'Scan', label: 'See your meal' },
  { path: '/preview/preferences', shortLabel: 'Taste', label: 'Set your taste' },
  { path: '/preview/discover', shortLabel: 'Discover', label: 'Follow a craving' },
  { path: '/preview/recommendation', shortLabel: 'Match', label: 'Find what fits' },
  { path: '/preview/swaps', shortLabel: 'Swap', label: 'Make it yours' },
  { path: '/preview/remember', shortLabel: 'Remember', label: 'Remember the good stuff' },
]

export const preferenceGroups = [
  { title: 'Cravings', choices: ['Something cozy', 'Fresh & bright', 'Savory', 'A little sweet'] },
  { title: 'How you eat', choices: ['Mostly plant-forward', 'Protein-minded', 'Gluten-conscious'] },
  { title: 'Make it work', choices: ['Weeknight easy', 'Budget-friendly', 'Cook once, enjoy twice'] },
]

export const discoveryMeals = [
  {
    name: 'Miso mushroom noodles',
    description: 'Silky, savory, and deeply cozy.',
    match: 'A warm match for your savory mood',
  },
  {
    name: 'Herby lentil bowl',
    description: 'Bright lemon, crisp greens, and a little crunch.',
    match: 'Fresh without feeling fussy',
  },
  {
    name: 'Roasted tomato & bean bowl',
    description: 'Jammy tomatoes, white beans, and peppery greens.',
    match: 'Easy to make your own',
  },
] as const

export const visibleFoods = [
  { name: 'Roasted squash', detail: 'likely' },
  { name: 'Herby grains', detail: 'likely' },
  { name: 'Tender greens', detail: 'likely' },
  { name: 'Creamy dressing', detail: 'possibly tahini-based' },
]

export const rememberedMeals = [
  { day: 'Tuesday', meal: 'Crispy tofu rice bowl', note: 'You liked the sesame-lime finish.' },
] as const
