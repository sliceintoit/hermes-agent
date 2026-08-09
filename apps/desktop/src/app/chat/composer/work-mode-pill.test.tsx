import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { $currentWorkMode, $freshDraftReady, $newChatWorkMode } from '@/store/session'

import { WorkModePill } from './work-mode-pill'

describe('WorkModePill', () => {
  afterEach(() => {
    cleanup()
    $currentWorkMode.set(null)
    $freshDraftReady.set(false)
    $newChatWorkMode.set('everyday')
  })

  it('shows the seed-stage selector only for a fresh conversation', async () => {
    $freshDraftReady.set(true)
    render(<WorkModePill disabled={false} />)

    const trigger = screen.getByRole('button', { name: 'Work mode: Everyday' })
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false })
    fireEvent.pointerUp(trigger, { button: 0, ctrlKey: false })

    expect(screen.getByText('Start a focused session')).toBeTruthy()
    expect(screen.getByText('Search & Read')).toBeTruthy()
    expect(screen.getByText('Build / Websites')).toBeTruthy()
    expect(screen.getByText('Automate')).toBeTruthy()
    expect(screen.getByText('More…')).toBeTruthy()

    fireEvent.click(screen.getByText('Build / Websites'))

    await waitFor(() => expect($newChatWorkMode.get()).toBe('build_websites'))
  })

  it('shows the active session mode without exposing a live capability toggle', () => {
    $freshDraftReady.set(false)
    $currentWorkMode.set('build_websites')
    render(<WorkModePill disabled={false} />)

    expect(screen.getByLabelText('Work mode: Build / Websites')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /work mode/i })).toBeNull()
  })
})
