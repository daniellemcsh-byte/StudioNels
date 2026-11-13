export interface TraitOption {
  id: string
  label: string
  prompt: string
}

export interface TraitGroup {
  id: string
  label: string
  options: TraitOption[]
}

export const CHARACTER_TRAITS: TraitGroup[] = [
  {
    id: 'skin',
    label: 'Skin',
    options: [
      { id: 'fair', label: 'Fair', prompt: 'fair porcelain skin' },
      { id: 'light', label: 'Light', prompt: 'light skin' },
      { id: 'medium', label: 'Medium', prompt: 'medium warm skin' },
      { id: 'tan', label: 'Tan', prompt: 'sun-kissed tan skin' },
      { id: 'brown', label: 'Brown', prompt: 'rich brown skin' },
      { id: 'deep', label: 'Deep', prompt: 'deep dark skin' },
    ],
  },
  {
    id: 'eyes',
    label: 'Eye colour',
    options: [
      { id: 'brown', label: 'Brown', prompt: 'brown eyes' },
      { id: 'hazel', label: 'Hazel', prompt: 'hazel eyes' },
      { id: 'green', label: 'Green', prompt: 'green eyes' },
      { id: 'blue', label: 'Blue', prompt: 'blue eyes' },
      { id: 'grey', label: 'Grey', prompt: 'grey eyes' },
      { id: 'amber', label: 'Amber', prompt: 'amber eyes' },
    ],
  },
  {
    id: 'hair_length',
    label: 'Hair length',
    options: [
      { id: 'bald', label: 'Bald', prompt: 'bald head' },
      { id: 'buzz', label: 'Buzz', prompt: 'buzz cut hair' },
      { id: 'short', label: 'Short', prompt: 'short hair' },
      { id: 'medium', label: 'Medium', prompt: 'medium-length hair' },
      { id: 'long', label: 'Long', prompt: 'long hair' },
      { id: 'very_long', label: 'Very long', prompt: 'very long flowing hair' },
    ],
  },
  {
    id: 'hair_colour',
    label: 'Hair colour',
    options: [
      { id: 'black', label: 'Black', prompt: 'black hair' },
      { id: 'dark_brown', label: 'Dark brown', prompt: 'dark brown hair' },
      { id: 'brown', label: 'Brown', prompt: 'brown hair' },
      { id: 'blonde', label: 'Blonde', prompt: 'blonde hair' },
      { id: 'red', label: 'Red', prompt: 'red hair' },
      { id: 'silver', label: 'Silver', prompt: 'silver hair' },
      { id: 'white', label: 'White', prompt: 'white hair' },
      { id: 'pink', label: 'Pink', prompt: 'pink dyed hair' },
      { id: 'blue', label: 'Blue', prompt: 'blue dyed hair' },
      { id: 'teal', label: 'Teal', prompt: 'teal dyed hair' },
    ],
  },
  {
    id: 'hair_style',
    label: 'Hair style',
    options: [
      { id: 'straight', label: 'Straight', prompt: 'straight hair' },
      { id: 'wavy', label: 'Wavy', prompt: 'wavy hair' },
      { id: 'curly', label: 'Curly', prompt: 'curly hair' },
      { id: 'coily', label: 'Coily', prompt: 'coily textured hair' },
      { id: 'braids', label: 'Braids', prompt: 'braided hair' },
      { id: 'bun', label: 'Bun', prompt: 'hair in a bun' },
      { id: 'ponytail', label: 'Ponytail', prompt: 'ponytail hairstyle' },
    ],
  },
  {
    id: 'body',
    label: 'Build',
    options: [
      { id: 'slim', label: 'Slim', prompt: 'slim build' },
      { id: 'athletic', label: 'Athletic', prompt: 'athletic build' },
      { id: 'average', label: 'Average', prompt: 'average build' },
      { id: 'soft', label: 'Soft', prompt: 'soft rounded build' },
      { id: 'stocky', label: 'Stocky', prompt: 'stocky strong build' },
    ],
  },
  {
    id: 'age',
    label: 'Age vibe',
    options: [
      { id: 'teen', label: 'Teen', prompt: 'teenage appearance' },
      { id: 'young', label: 'Young adult', prompt: 'young adult' },
      { id: 'adult', label: 'Adult', prompt: 'adult in their thirties' },
      { id: 'middle', label: 'Middle age', prompt: 'middle-aged adult' },
      { id: 'elder', label: 'Elder', prompt: 'elderly face with character' },
    ],
  },
  {
    id: 'vibe',
    label: 'Vibe',
    options: [
      { id: 'soft', label: 'Soft', prompt: 'gentle soft expression' },
      { id: 'cool', label: 'Cool', prompt: 'cool confident expression' },
      { id: 'mysterious', label: 'Mysterious', prompt: 'mysterious intense gaze' },
      { id: 'warm', label: 'Warm', prompt: 'warm friendly expression' },
      { id: 'fierce', label: 'Fierce', prompt: 'fierce determined look' },
    ],
  },
]

export const DEFAULT_TRAITS: Record<string, string> = {
  skin: 'medium',
  eyes: 'brown',
  hair_length: 'medium',
  hair_colour: 'dark_brown',
  hair_style: 'wavy',
  body: 'average',
  age: 'young',
  vibe: 'cool',
}

export function buildCharacterPrompt(
  name: string,
  traits: Record<string, string>,
  extra: string,
  styleSuffix?: string,
): { look: string; prompt: string } {
  const bits: string[] = []
  for (const group of CHARACTER_TRAITS) {
    const opt = group.options.find((o) => o.id === traits[group.id])
    if (opt) bits.push(opt.prompt)
  }
  if (extra.trim()) bits.push(extra.trim())
  const look = bits.join(', ')
  const who = name.trim() || 'unnamed character'
  const prompt = [
    `character portrait of ${who}`,
    look,
    'coherent face, clear features, studio character sheet, front three-quarter view',
    styleSuffix || 'cinematic lighting',
  ]
    .filter(Boolean)
    .join(', ')
  return { look, prompt }
}
