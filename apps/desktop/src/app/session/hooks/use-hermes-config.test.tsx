import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getHermesConfig, getHermesConfigDefaults } from '@/hermes'
import {
  $currentFastMode,
  $currentReasoningEffort,
  markComposerSelectionManual,
  setCurrentFastMode,
  setCurrentReasoningEffort
} from '@/store/session'

import { useHermesConfig } from './use-hermes-config'

vi.mock('@/hermes', () => ({
  getHermesConfig: vi.fn(),
  getHermesConfigDefaults: vi.fn()
}))

describe('useHermesConfig selector races', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    setCurrentReasoningEffort('')
    setCurrentFastMode(false)
  })

  it('does not overwrite a picker change with an older config refresh', async () => {
    let resolveConfig!: (value: {
      agent: { reasoning_effort: string; service_tier: string }
      display: Record<string, never>
      terminal: Record<string, never>
    }) => void

    vi.mocked(getHermesConfig).mockReturnValue(
      new Promise(resolve => {
        resolveConfig = resolve
      })
    )
    vi.mocked(getHermesConfigDefaults).mockResolvedValue({})

    const activeSessionIdRef = { current: null as string | null }
    const { result } = renderHook(() =>
      useHermesConfig({ activeSessionIdRef, refreshProjectBranch: vi.fn().mockResolvedValue(undefined) })
    )

    const refresh = result.current.refreshHermesConfig()

    act(() => {
      markComposerSelectionManual()
      setCurrentReasoningEffort('high')
      setCurrentFastMode(true)
    })

    resolveConfig({
      agent: { reasoning_effort: 'low', service_tier: 'normal' },
      display: {},
      terminal: {}
    })
    await refresh

    expect($currentReasoningEffort.get()).toBe('high')
    expect($currentFastMode.get()).toBe(true)
  })
})
