export const WORK_MODES = [
  {
    description: 'General computer work with the smallest context.',
    id: 'everyday',
    label: 'Everyday'
  },
  {
    description: 'Find and read online information, documents, and visuals.',
    id: 'search_read',
    label: 'Search & Read'
  },
  {
    description: 'Code and test software, browse sites, and use signed-in sessions.',
    id: 'build_websites',
    label: 'Build / Websites'
  },
  {
    description: 'Create scripts, scheduled jobs, and multi-step workflows.',
    id: 'automate',
    label: 'Automate'
  },
  {
    description: 'Use specialist integrations already configured in Tools.',
    id: 'more',
    label: 'More…'
  }
] as const

export type WorkMode = (typeof WORK_MODES)[number]['id']

export const DEFAULT_WORK_MODE: WorkMode = 'everyday'

export const isWorkMode = (value: unknown): value is WorkMode =>
  typeof value === 'string' && WORK_MODES.some(mode => mode.id === value)

export const workModeLabel = (value: null | string | undefined): string =>
  WORK_MODES.find(mode => mode.id === value)?.label ?? 'Everyday'
