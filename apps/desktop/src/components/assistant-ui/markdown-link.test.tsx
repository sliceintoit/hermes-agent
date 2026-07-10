import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MarkdownLink } from './markdown-text'

const desktopWindow = window as unknown as { hermesDesktop?: Window['hermesDesktop'] }
const initialHermesDesktop = desktopWindow.hermesDesktop

afterEach(() => {
  vi.restoreAllMocks()
  cleanup()

  if (initialHermesDesktop) {
    desktopWindow.hermesDesktop = initialHermesDesktop
  } else {
    delete desktopWindow.hermesDesktop
  }
})

describe('MarkdownLink', () => {
  it('opens file URLs through the validated desktop bridge', () => {
    const openExternal = vi.fn().mockResolvedValue(undefined)

    desktopWindow.hermesDesktop = {
      openExternal
    } as unknown as Window['hermesDesktop']

    render(
      <MarkdownLink href="file:///Users/hermes/report.html">Open local report</MarkdownLink>
    )

    fireEvent.click(screen.getByRole('link', { name: 'Open local report' }))

    expect(openExternal).toHaveBeenCalledOnce()
    expect(openExternal).toHaveBeenCalledWith('file:///Users/hermes/report.html')
  })

  it('leaves ordinary relative links on the renderer path', () => {
    const openExternal = vi.fn().mockResolvedValue(undefined)

    desktopWindow.hermesDesktop = {
      openExternal
    } as unknown as Window['hermesDesktop']

    render(<MarkdownLink href="/settings">Open settings</MarkdownLink>)

    fireEvent.click(screen.getByRole('link', { name: 'Open settings' }))

    expect(openExternal).not.toHaveBeenCalled()
  })
})