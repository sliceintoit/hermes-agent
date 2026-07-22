import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SessionInfo } from '@/types/hermes'

import { $selectedStoredSessionId, $sessions } from './session'
import {
  $switcherIndex,
  $switcherOpen,
  $switcherSessions,
  closeSwitcher,
  commitOnCtrlUp,
  getSessionSwitcherDotTone,
  onSwitcherTabDown,
  onSwitcherTabUp,
  openOrAdvanceSwitcher,
  slotSessionId,
  SWITCHER_REVEAL_MS
} from './session-switcher'

const session = (id: string): SessionInfo => ({ id }) as SessionInfo

const seed = (ids: string[], selected: null | string) => {
  $sessions.set(ids.map(session))
  $selectedStoredSessionId.set(selected)
}

const tabTap = (direction: 1 | -1 = 1) => {
  onSwitcherTabDown()
  const target = openOrAdvanceSwitcher(direction)
  onSwitcherTabUp()

  return target
}

beforeEach(() => {
  vi.useRealTimers()
  closeSwitcher()
  $switcherSessions.set([])
  $switcherIndex.set(0)
})

afterEach(() => {
  seed([], null)
})

describe('openOrAdvanceSwitcher', () => {
  it('does nothing with fewer than two sessions', () => {
    seed(['a'], 'a')
    onSwitcherTabDown()

    expect(openOrAdvanceSwitcher(1)).toBeNull()
  })

  it('jumps immediately on a quick Tab tap without opening the HUD', () => {
    seed(['a', 'b', 'c'], 'a')

    expect(tabTap()).toBe('b')
    expect($switcherOpen.get()).toBe(false)
    expect(commitOnCtrlUp()).toBeNull()
  })

  it('does not open the HUD when Ctrl stays down but Tab was released quickly', () => {
    vi.useFakeTimers()
    seed(['a', 'b', 'c'], 'a')

    tabTap()
    vi.advanceTimersByTime(SWITCHER_REVEAL_MS)

    expect($switcherOpen.get()).toBe(false)
  })

  it('opens the HUD when Tab stays held past the reveal delay', () => {
    vi.useFakeTimers()
    seed(['a', 'b', 'c'], 'a')

    onSwitcherTabDown()
    openOrAdvanceSwitcher(1)
    vi.advanceTimersByTime(SWITCHER_REVEAL_MS)

    expect($switcherOpen.get()).toBe(true)
    onSwitcherTabUp()
  })

  it('opens on a second Tab while Ctrl is still down', () => {
    seed(['a', 'b', 'c'], 'a')

    expect(tabTap()).toBe('b')
    onSwitcherTabDown()
    openOrAdvanceSwitcher(1)
    onSwitcherTabUp()

    expect($switcherOpen.get()).toBe(true)
    expect($switcherIndex.get()).toBe(2)
  })

  it('commits the HUD highlight on Ctrl up', () => {
    seed(['a', 'b', 'c'], 'a')

    expect(tabTap()).toBe('b')
    onSwitcherTabDown()
    openOrAdvanceSwitcher(1)
    onSwitcherTabUp()

    expect(commitOnCtrlUp()).toBe('c')
  })
})

describe('getSessionSwitcherDotTone', () => {
  it('prioritizes attention over every other state', () => {
    expect(
      getSessionSwitcherDotTone({
        attention: true,
        backgroundRunning: true,
        unread: true,
        working: true
      })
    ).toBe('attention')
  })

  it('uses the blue active state for an LLM turn even when a process is also running', () => {
    expect(
      getSessionSwitcherDotTone({
        attention: false,
        backgroundRunning: true,
        unread: false,
        working: true
      })
    ).toBe('active-working')
  })

  it('uses the gray background state for a live process after the LLM turn settles', () => {
    expect(
      getSessionSwitcherDotTone({
        attention: false,
        backgroundRunning: true,
        unread: true,
        working: false
      })
    ).toBe('background-working')
  })

  it('uses the green unread state after a finished session settles', () => {
    expect(
      getSessionSwitcherDotTone({
        attention: false,
        backgroundRunning: false,
        unread: true,
        working: false
      })
    ).toBe('finished-unread')
  })
})

describe('slotSessionId', () => {
  it('reads the armed snapshot while browsing is pending', () => {
    seed(['a', 'b', 'c'], 'a')
    tabTap()
    $sessions.set([session('x')])

    expect(slotSessionId(2)).toBe('b')
  })
})
