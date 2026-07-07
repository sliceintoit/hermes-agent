import { render, waitFor } from '@testing-library/react'
import type { MutableRefObject } from 'react'
import { useEffect, useRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

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
  const ref = <T,>(value: T): MutableRefObject<T> => ({ current: value })
  const activeSessionIdRef = ref<string | null>('runtime-1')
  const sessionStateByRuntimeIdRef = ref(new Map<string, ClientSessionState>())

  const { handleGatewayEvent } = useMessageStream({
    activeSessionIdRef,
    hydrateFromStoredSession: vi.fn().mockResolvedValue(undefined),
    onSessionRotated,
    queryClient: {} as never,
    refreshHermesConfig: vi.fn().mockResolvedValue(undefined),
    refreshSessions: vi.fn().mockResolvedValue(undefined),
    sessionStateByRuntimeIdRef,
    updateSessionState: (_sessionId, updater) => updater({} as ClientSessionState)
  })

  useEffect(() => {
    onReady(handleGatewayEvent)
  }, [handleGatewayEvent, onReady])

  return null
}

afterEach(() => {
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
