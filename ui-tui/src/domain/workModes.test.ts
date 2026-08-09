import { describe, expect, it } from 'vitest'

import { DEFAULT_WORK_MODE, isWorkMode, WORK_MODES, workModeLabel } from './workModes.js'

describe('Desktop work modes', () => {
  it('keeps the seed selector small and human-oriented', () => {
    expect(WORK_MODES.map(mode => mode.id)).toEqual([
      'everyday',
      'search_read',
      'build_websites',
      'automate',
      'more'
    ])
    expect(DEFAULT_WORK_MODE).toBe('everyday')
  })

  it('validates persisted selector ids and renders their labels', () => {
    expect(isWorkMode('search_read')).toBe(true)
    expect(isWorkMode('not-a-mode')).toBe(false)
    expect(workModeLabel('build_websites')).toBe('Build / Websites')
    expect(workModeLabel('unknown')).toBe('Everyday')
  })
})
