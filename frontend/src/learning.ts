import type { TabId } from './types'

export type LearnSectionId =
  | 'start-here'
  | 'words'
  | 'first-film'
  | 'generate'
  | 'characters'
  | 'continue'
  | 'audio'
  | 'edit'
  | 'folders'
  | 'personal'
  | 'gpu'
  | 'agent'

export interface LearnHowTo {
  title: string
  steps: string[]
  example?: string
}

export interface LearnTopic {
  id: LearnSectionId
  title: string
  blurb: string
  where: { label: string; tab?: TabId; detail: string }[]
  howto: LearnHowTo[]
  examples: string[]
  tip?: string
}

export const LEARN_TOPICS: LearnTopic[] = [
  {
    id: 'start-here',
    title: 'Start here (first time with AI?)',
    blurb:
      'Nellwright is VIPNells’s local film studio. You describe a story in plain English, it breaks that into shots, then your computer (or a preview) turns those into images and clips. You do not need to know coding or “prompt engineering.”',
    where: [
      { label: 'Inspiration', tab: 'inspiration', detail: 'Side nav → Start → Inspiration' },
      { label: 'New project', detail: 'Projects screen → New project' },
      { label: 'Learning (this page)', tab: 'learning', detail: 'Side nav → System → Learning' },
    ],
    howto: [
      {
        title: 'Make your first tiny film in 5 steps',
        steps: [
          'Create a project (pick Short film).',
          'Open Agent and type a simple idea, e.g. “A kid finds a glowing key in a rainy alley.”',
          'Wait for the shot list — edit any line you dislike.',
          'Open Generate (or hit Continue all shots) and run one shot first.',
          'Open Sampling, pin your favourite take, then Director to arrange the cut.',
        ],
        example: 'Idea: “Claymation fox baking bread at dawn.”',
      },
    ],
    examples: [
      'Keep ideas short and visual: who, where, what happens.',
      'One shot ≈ one camera beat (a few seconds), not a whole movie.',
      'If nothing looks “real” yet, you may be in preview mode — that’s OK while learning.',
    ],
    tip: 'Treat the first run as a sketch. AI video is draft → pick → improve.',
  },
  {
    id: 'words',
    title: 'Words you’ll see (plain English)',
    blurb: 'Jargon translated so nothing feels mysterious.',
    where: [{ label: 'Everywhere', detail: 'Hover badges and read the tiny muted hints under panels.' }],
    howto: [
      {
        title: 'Cheat sheet',
        steps: [
          'Prompt = the text description the AI draws/films from.',
          'Model = the “brain” file that knows how to make pictures/video (like choosing a camera stock).',
          'LoRA = a small add-on style/face pack you drop in loras/.',
          't2i / t2v / i2v = text→image, text→video, image→video (continue from a still).',
          'Take = one attempt at a shot. Pin the good one.',
          'VRAM = GPU memory. Bigger models need more.',
        ],
      },
    ],
    examples: [
      't2v: “wide shot of neon market at night, rain, handheld”',
      'i2v: start from last frame so the next clip matches the previous one',
    ],
  },
  {
    id: 'first-film',
    title: 'How-to: plan a story with the Agent',
    blurb:
      'The Agent is your friendly director assistant. Free offline built-in planner, local Ollama, or a paid API in Settings.',
    where: [
      { label: 'Agent', tab: 'agent', detail: 'Side nav → Start → Agent' },
      { label: 'Agent LLM', tab: 'settings', detail: 'System → Settings → Agent LLM' },
    ],
    howto: [
      {
        title: 'Plan shots from an idea',
        steps: [
          'Optionally add characters in Profiles / Creator first.',
          'Set Time & Style (length + look: cinematic, clay, cartoon…).',
          'In Agent, describe the story in 1–3 sentences.',
          'Leave “replace shots” on for a fresh list, or off to append.',
          'Review Shots — fix dialogue, camera, duration.',
        ],
        example: '“30-second ad: sneakers splash through puddles, end on logo.”',
      },
    ],
    examples: [
      'Music video: “neon subway dance, 45 seconds, high energy cuts.”',
      'If the paid API fails, Nellwright falls back to the built-in planner.',
    ],
  },
  {
    id: 'generate',
    title: 'How-to: Generate images & video',
    blurb: 'This is the make button. Pick a mode, a model, optional LoRA, check “Can my GPU do this?”, then queue.',
    where: [
      { label: 'Generate', tab: 'generate', detail: 'Side nav → Make → Generate' },
      { label: 'Models / LoRAs', tab: 'models', detail: 'Make → Models' },
    ],
    howto: [
      {
        title: 'Run one safe test shot',
        steps: [
          'Mode: Text to video (t2v) or Text to image (t2i).',
          'Quality: Draft while learning.',
          'Attach to a shot from the dropdown so the result lands in Sampling.',
          'Read the GPU panel — ETA and VRAM fit — before Generate.',
          'Watch Queue on the right until status is done.',
        ],
        example: '768×432, draft, 3 seconds — friendly on smaller GPUs.',
      },
      {
        title: 'Use a LoRA without pasting paths',
        steps: [
          'Drop a .safetensors file into the app’s loras/ folder.',
          'In Generate, open Optional LoRA → Refresh folder.',
          'Pick it from the dropdown and set strength (~0.7–0.9).',
        ],
      },
    ],
    examples: [
      'Start without a LoRA. Add style packs once the base look works.',
      '“Can my GPU do this?” saying won’t fit → lower resolution or switch model.',
    ],
  },
  {
    id: 'characters',
    title: 'How-to: keep the same character',
    blurb: 'AI forgets faces easily. Character lock + Continuity teach it what must stay the same.',
    where: [
      { label: 'Creator', tab: 'creator', detail: 'Start → Creator' },
      { label: 'Profiles', tab: 'profiles', detail: 'Start → Profiles' },
      { label: 'Continuity', tab: 'continuity', detail: 'Edit → Continuity' },
    ],
    howto: [
      {
        title: 'Lock a look',
        steps: [
          'In Creator/Profiles, write a Character lock: hair, age, clothing, unique detail.',
          'Generate a character still and keep that reference.',
          'Link the character to shots.',
          'Open Continuity → Save & rescore after takes exist.',
        ],
        example: 'Lock: “teen girl, copper braid, green raincoat, freckles, silver fox pin”',
      },
    ],
    examples: [
      'One lock phrase reused in every shot prompt beats reinventing the face each time.',
      'Rejected takes = continuity score below your threshold — rewrite or re-pin.',
    ],
  },
  {
    id: 'continue',
    title: 'How-to: continue from the last video',
    blurb:
      'Video continuation chains shots: each new clip starts from the last frame of the previous take (image-to-video), so scenes feel like one world.',
    where: [
      { label: 'Shots toggle', tab: 'shots', detail: 'Story → Shots → “Continue each shot…”' },
      { label: 'Generate checkbox', tab: 'generate', detail: 'Make → Generate → Continue from previous…' },
      { label: 'Top bar', detail: '“Continue all shots” when chain is on' },
    ],
    howto: [
      {
        title: 'Chain a whole sequence',
        steps: [
          'Turn on Continue each shot from the last frame…',
          'Generate shot 1 first (or Continue all shots).',
          'Later shots queue as i2v automatically after the previous finishes.',
          'Pin winners in Sampling / promote Rehearsal takes.',
        ],
        example: 'Shot 1 alley → Shot 2 same alley, character turns — last frame carries the set.',
      },
    ],
    examples: [
      'First shot of a brand-new project has no previous frame → starts as text-to-video.',
      'Turn chain off if you want every shot independent.',
    ],
  },
  {
    id: 'audio',
    title: 'How-to: voice, accents & music',
    blurb: 'Audio tab sketches voice beds and music moods. Pair with your visual style.',
    where: [{ label: 'Audio', tab: 'audio', detail: 'Make → Audio' }],
    howto: [
      {
        title: 'Add a bed under a scene',
        steps: [
          'Pick music mood or accent/voice notes.',
          'Generate audio (t2a) or note accents for later VO.',
          'Keep audio format in Time & Style (wav/mp3).',
        ],
      },
    ],
    examples: ['Soft piano bed under a clay short.', 'Accent note: “warm Scottish narrator, unhurried.”'],
  },
  {
    id: 'edit',
    title: 'How-to: Director — cut, captions, filters',
    blurb:
      'Director is your in-app edit bay: timeline playhead, cut/trim/speed, editable captions, look filters, then export.',
    where: [
      { label: 'Rehearsal', tab: 'rehearsal', detail: 'Edit → Rehearsal' },
      { label: 'Sampling', tab: 'sampling', detail: 'Edit → Sampling' },
      { label: 'Director', tab: 'director', detail: 'Edit → Director' },
    ],
    howto: [
      {
        title: 'Build and trim a cut',
        steps: [
          'Pin takes in Sampling, then Director → Build video from pins.',
          'Zoom the timeline (px/s) to cut fine points; Split at playhead.',
          'Use In−/In+/Out−/Out+ for frame-fine trims; Zoom/Pan like TikTok.',
          'Add audio under video: upload or pick a finished Audio-tab bed at the playhead.',
          'Two audio lanes: Music bed + VO/SFX. Mute/volume per clip.',
          'Filters overlay the preview; captions sit on the phone-style viewer.',
          'Download .srt and/or Export EDL / FCPXML (includes audio markers).',
        ],
        example: 'Playhead 0:04.2 → Split · Audio bed from score · Filter Neon · Zoom 130%',
      },
    ],
    examples: [
      'Higher zoom = finer snap steps (0.05s).',
      'Audio track 1 = music, track 2 = voice/SFX layered on top.',
    ],
  },
  {
    id: 'folders',
    title: 'Where files live (Pinokio-style)',
    blurb: 'Everything sits in the Nellwright folder you downloaded — no mystery hidden paths.',
    where: [{ label: 'Info', tab: 'info', detail: 'System → Info' }],
    howto: [
      {
        title: 'Folder map',
        steps: [
          'models/ — AI checkpoints',
          'loras/ — style/character LoRAs (auto dropdown)',
          'outputs/ — everything you generate',
          'uploads/ — your reference images/clips',
          'projects/ — saved studio JSON',
          'addons/ — plugins & skills',
        ],
      },
    ],
    examples: ['Drop my_style.safetensors into loras/ → Refresh in Generate.'],
  },
  {
    id: 'personal',
    title: 'Your GitHub & Hugging Face',
    blurb:
      'Save your profile URLs so Nellwright knows where “your stuff” lives. Paste a model or LoRA link to pull it into the local folders, or point teammates at your repos.',
    where: [
      { label: 'My links', tab: 'sources', detail: 'System → My links' },
      { label: 'Settings', tab: 'settings', detail: 'Also stored with Settings' },
    ],
    howto: [
      {
        title: 'Personalise + import',
        steps: [
          'Open My links and paste your Hugging Face profile (https://huggingface.co/you).',
          'Paste your GitHub profile or studio repo URL.',
          'Optional: HF token (read) if the model is gated.',
          'In Import, paste a model repo (owner/name) or full HF / GitHub file URL.',
          'Choose Models, LoRAs, or Add-ons → Import to local folder.',
        ],
        example: 'HF: https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B-Diffusers',
      },
    ],
    examples: [
      'GitHub raw LoRA URL → imports into loras/.',
      'Your HF collection URL is saved so you remember where your packs live.',
    ],
    tip: 'Tokens stay on your machine in local settings — not uploaded to Nellwright cloud.',
  },
  {
    id: 'gpu',
    title: 'GPU, presets & “will this run?”',
    blurb: 'Honest fit before you queue. R9700 32GB friends can use the big preset; shareable builds use Low VRAM.',
    where: [
      { label: 'GPU panel', tab: 'generate', detail: 'Generate → Can my GPU do this?' },
      { label: 'Preset', tab: 'settings', detail: 'Settings → Compute preset' },
    ],
    howto: [
      {
        title: 'If it says won’t fit',
        steps: [
          'Switch to a smaller model (e.g. Wan 1.3B).',
          'Lower width/height and use Draft.',
          'Keep CPU offload on.',
          'Shorten clip length / frames.',
        ],
      },
    ],
    examples: ['Comfortable = green light. Tight = one job at a time. Preview only = install ROCm PyTorch later.'],
  },
  {
    id: 'agent',
    title: 'Paid vs free Agent brains',
    blurb: 'Built-in and Ollama are free/local. OpenAI, Anthropic, OpenRouter, or a custom OpenAI-compatible URL are optional paid upgrades for smarter shot lists.',
    where: [{ label: 'Settings', tab: 'settings', detail: 'System → Settings → Agent LLM' }],
    howto: [
      {
        title: 'Plug in a paid key',
        steps: [
          'Pick OpenAI / Anthropic / OpenRouter / Custom.',
          'Paste API key (leave blank later to keep the saved one).',
          'Set model id (e.g. gpt-4o-mini).',
          'Save — Agent uses it next plan. Failures fall back to built-in.',
        ],
      },
    ],
    examples: ['OpenRouter: one key, many models.', 'Custom: any host that speaks Chat Completions.'],
  },
]

export const LEARN_NAV = LEARN_TOPICS.map((t) => ({ id: t.id, title: t.title }))
