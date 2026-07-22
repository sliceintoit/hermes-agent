import { useStore } from '@nanostores/react'
import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'

import { sessionTitle } from '@/lib/chat-runtime'
import { cn } from '@/lib/utils'
import { $backgroundRunningSessionIds } from '@/store/composer-status'
import { $attentionSessionIds, $unreadFinishedSessionIds, $workingSessionIds } from '@/store/session'
import {
  $switcherIndex,
  $switcherOpen,
  $switcherSessions,
  closeSwitcher,
  getSessionSwitcherDotTone
} from '@/store/session-switcher'

import { HUD_ITEM, HUD_POSITION, HUD_SURFACE, HUD_TEXT } from './floating-hud'
import { sessionRoute } from './routes'

// Compact session-switcher HUD — keyboard-driven from `use-keybinds`, rows
// clickable via mousedown (Ctrl+click on macOS). No Dialog: Tab stays global.
export function SessionSwitcher() {
  const open = useStore($switcherOpen)
  const sessions = useStore($switcherSessions)
  const index = useStore($switcherIndex)
  const working = useStore($workingSessionIds)
  const backgroundRunning = useStore($backgroundRunningSessionIds)
  const attention = useStore($attentionSessionIds)
  const unread = useStore($unreadFinishedSessionIds)
  const navigate = useNavigate()

  const activeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest' })
  }, [index, open])

  if (!open || sessions.length === 0) {
    return null
  }

  const workingIds = new Set(working)
  const backgroundRunningIds = new Set(backgroundRunning)
  const attentionIds = new Set(attention)
  const unreadIds = new Set(unread)

  const pick = (sessionId: string) => {
    closeSwitcher()
    navigate(sessionRoute(sessionId))
  }

  return createPortal(
    <>
      {/* Transparent click-catcher: click-away closes, but no dim/blur. */}
      <div
        className="fixed inset-0 z-[219]"
        onMouseDown={e => {
          e.preventDefault()
          closeSwitcher()
        }}
      />
      <div
        className={cn(
          HUD_POSITION,
          HUD_SURFACE,
          'dt-portal-scrollbar z-[220] max-h-[min(22rem,64vh)] w-[min(19rem,calc(100vw-2rem))] select-none overflow-y-auto p-1'
        )}
      >
        {sessions.map((session, i) => {
          const selected = i === index
          return (
            <div
              className={cn(
                'flex cursor-pointer items-center rounded leading-tight',
                HUD_ITEM,
                HUD_TEXT,
                selected ? 'bg-accent text-accent-foreground' : 'text-(--ui-text-secondary) hover:bg-(--ui-row-hover-background)'
              )}
              key={session.id}
              onMouseDown={e => {
                e.preventDefault()
                pick(session.id)
              }}
              ref={selected ? activeRef : undefined}
            >
              <SwitcherDot
                attention={attentionIds.has(session.id)}
                backgroundRunning={backgroundRunningIds.has(session.id)}
                unread={unreadIds.has(session.id)}
                working={workingIds.has(session.id)}
              />
              <span className="min-w-0 flex-1 truncate">{sessionTitle(session)}</span>
              {i < 9 && (
                <span
                  className={cn(
                    'shrink-0 font-mono text-[0.625rem] tabular-nums',
                    selected ? 'text-accent-foreground/70' : 'text-(--ui-text-quaternary)'
                  )}
                >
                  ⌃{i + 1}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </>,
    document.body
  )
}

function SwitcherDot({
  attention,
  backgroundRunning,
  unread,
  working
}: {
  attention: boolean
  backgroundRunning: boolean
  unread: boolean
  working: boolean
}) {
  const tone = getSessionSwitcherDotTone({ attention, backgroundRunning, unread, working })

  return (
    <span
      className={cn(
        'size-1 shrink-0 rounded-full',
        tone === 'attention' && 'bg-amber-400',
        tone === 'active-working' &&
          "relative bg-(--ui-accent) shadow-[0_0_0.625rem_color-mix(in_srgb,var(--ui-accent)_55%,transparent)] before:absolute before:inset-0 before:animate-ping before:rounded-full before:bg-(--ui-accent) before:opacity-70 before:content-['']",
        tone === 'background-working' &&
          "relative bg-(--ui-text-quaternary) opacity-80 shadow-[0_0_0.625rem_color-mix(in_srgb,var(--ui-text-quaternary)_45%,transparent)] before:absolute before:inset-0 before:animate-ping before:rounded-full before:bg-(--ui-text-quaternary) before:opacity-60 before:content-['']",
        tone === 'finished-unread' && 'bg-emerald-500',
        tone === 'idle' && 'bg-(--ui-text-quaternary)/50'
      )}
    />
  )
}
