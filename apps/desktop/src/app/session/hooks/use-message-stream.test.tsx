import { act, cleanup, render, waitFor } from '@testing-library/react'
import { useEffect, useRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createClientSessionState } from '@/lib/chat-runtime'
import { $compactingSessions } from '@/store/compaction'
import type { RpcEvent } from '@/types/hermes'

import type { ClientSessionState } from '../../types'

import { useMessageStream } from './use-message-stream'

function Harness({
  onReady,
  onSessionRotated
}: {
  onReady: (handleGatewayEvent: (event: RpcEvent) => void) => void
  onSessionRotated?: (event: { oldSessionKey: string; runtimeSessionId: string; sessionKey: string }) => void
}) {
  const activeSessionIdRef = useRef<string | null>('runtime-1')
  const sessionStateByRuntimeIdRef = useRef(new Map<string, ClientSessionState>())

  const { handleGatewayEvent } = useMessageStream({
    activeSessionIdRef,
    hydrateFromStoredSession: vi.fn().mockResolvedValue(undefined),
    onSessionRotated,
    queryClient: {} as never,
    refreshHermesConfig: vi.fn().mockResolvedValue(undefined),
    refreshSessions: vi.fn().mockResolvedValue(undefined),
    sessionStateByRuntimeIdRef,
    updateSessionState: (sessionId, updater) => {
      const current = sessionStateByRuntimeIdRef.current.get(sessionId) ?? createClientSessionState()
      const next = updater(current)

      sessionStateByRuntimeIdRef.current.set(sessionId, next)

      return next
    }
  })

  useEffect(() => {
    onReady(handleGatewayEvent)
  }, [handleGatewayEvent, onReady])

  return null
}

afterEach(() => {
  cleanup()
  $compactingSessions.set({})
  vi.restoreAllMocks()
})

describe('useMessageStream session.rotated handling', () => {
  it('invokes onSessionRotated with old and new stored session keys', async () => {
    const onSessionRotated = vi.fn()
    let handleGatewayEvent: ((event: RpcEvent) => void) | null = null

    render(
      <Harness
        onReady={handler => {
          handleGatewayEvent = handler
        }}
        onSessionRotated={onSessionRotated}
      />
    )

    await waitFor(() => expect(handleGatewayEvent).not.toBeNull())

    handleGatewayEvent!({
      type: 'session.rotated',
      session_id: 'runtime-1',
      payload: {
        old_session_key: 'stored-parent',
        session_key: 'stored-child',
        runtime_session_id: 'runtime-1'
      }
    })

    expect(onSessionRotated).toHaveBeenCalledWith({
      oldSessionKey: 'stored-parent',
      runtimeSessionId: 'runtime-1',
      sessionKey: 'stored-child'
    })
  })

  it('ignores rotation events with missing or identical keys', async () => {
    const onSessionRotated = vi.fn()
    let handleGatewayEvent: ((event: RpcEvent) => void) | null = null

    render(
      <Harness
        onReady={handler => {
          handleGatewayEvent = handler
        }}
        onSessionRotated={onSessionRotated}
      />
    )

    await waitFor(() => expect(handleGatewayEvent).not.toBeNull())

    handleGatewayEvent!({
      type: 'session.rotated',
      session_id: 'runtime-1',
      payload: {
        old_session_key: 'stored-same',
        session_key: 'stored-same',
        runtime_session_id: 'runtime-1'
      }
    })

    expect(onSessionRotated).not.toHaveBeenCalled()
  })
})

describe('useMessageStream compaction lifecycle', () => {
  it('clears compaction when the gateway reports ready without requiring content', async () => {
    let handleGatewayEvent: ((event: RpcEvent) => void) | null = null

    render(<Harness onReady={handler => (handleGatewayEvent = handler)} />)
    await waitFor(() => expect(handleGatewayEvent).not.toBeNull())

    act(() => {
      handleGatewayEvent!({
        payload: { kind: 'compacting' },
        session_id: 'session-a',
        type: 'status.update'
      })
    })
    expect($compactingSessions.get()).toEqual({ 'session-a': true })

    act(() => {
      handleGatewayEvent!({ payload: { kind: 'ready' }, session_id: 'session-a', type: 'status.update' })
    })
    expect($compactingSessions.get()).toEqual({})
  })

  it('clears compaction when model or tool activity resumes', async () => {
    let handleGatewayEvent: ((event: RpcEvent) => void) | null = null

    const activityEvents: RpcEvent[] = [
      { payload: { text: 'continued' }, session_id: 'session-a', type: 'message.delta' },
      { payload: { text: 'thinking' }, session_id: 'session-a', type: 'thinking.delta' },
      { payload: { text: 'reasoning' }, session_id: 'session-a', type: 'reasoning.delta' },
      { payload: { text: 'reasoning' }, session_id: 'session-a', type: 'reasoning.available' },
      { payload: { name: 'terminal', tool_id: 'tool-1' }, session_id: 'session-a', type: 'tool.start' },
      { payload: { name: 'terminal', tool_id: 'tool-1' }, session_id: 'session-a', type: 'tool.progress' },
      { payload: { name: 'terminal', tool_id: 'tool-1' }, session_id: 'session-a', type: 'tool.generating' },
      { payload: { name: 'terminal', tool_id: 'tool-1' }, session_id: 'session-a', type: 'tool.complete' }
    ]

    render(<Harness onReady={handler => (handleGatewayEvent = handler)} />)
    await waitFor(() => expect(handleGatewayEvent).not.toBeNull())

    for (const event of activityEvents) {
      act(() => {
        handleGatewayEvent!({
          payload: { kind: 'compacting' },
          session_id: 'session-a',
          type: 'status.update'
        })
        handleGatewayEvent!(event)
      })
      expect($compactingSessions.get(), event.type).toEqual({})
    }
  })

  it('clears only the session targeted by the terminal event', async () => {
    let handleGatewayEvent: ((event: RpcEvent) => void) | null = null

    render(<Harness onReady={handler => (handleGatewayEvent = handler)} />)
    await waitFor(() => expect(handleGatewayEvent).not.toBeNull())

    act(() => {
      handleGatewayEvent!({
        payload: { kind: 'compacting' },
        session_id: 'session-a',
        type: 'status.update'
      })
      handleGatewayEvent!({
        payload: { kind: 'compacting' },
        session_id: 'session-b',
        type: 'status.update'
      })
      handleGatewayEvent!({ payload: { kind: 'ready' }, session_id: 'session-b', type: 'status.update' })
    })

    expect($compactingSessions.get()).toEqual({ 'session-a': true })
  })
})
