export const DESKTOP_WORK_MODES = [
  {
    description: 'General computer work with the smallest context.',
    id: 'everyday',
    label: 'Everyday'
  },
  {
    description: 'Find and read online information; analyze images, charts, screenshots, and visual documents.',
    id: 'search_read',
    label: 'Search & Read'
  },
  {
    description: 'Build and test software; work in public or signed-in websites; analyze screenshots.',
    id: 'build_websites',
    label: 'Build / Websites'
  },
  {
    description: 'Create scripts, recurring jobs, and delegated multi-step workflows.',
    id: 'automate',
    label: 'Automate'
  },
  {
    description: 'Use specialist integrations you have already configured.',
    id: 'more',
    label: 'More…'
  }
] as const

export type DesktopWorkMode = (typeof DESKTOP_WORK_MODES)[number]['id']

export const DEFAULT_DESKTOP_WORK_MODE: DesktopWorkMode = 'everyday'

export const isDesktopWorkMode = (value: unknown): value is DesktopWorkMode =>
  typeof value === 'string' && DESKTOP_WORK_MODES.some(mode => mode.id === value)

export function desktopWorkModeLabel(value: string | null | undefined): string {
  return DESKTOP_WORK_MODES.find(mode => mode.id === value)?.label ?? 'Everyday'
}
