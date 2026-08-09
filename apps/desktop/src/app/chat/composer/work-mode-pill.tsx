import { useStore } from '@nanostores/react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { ChevronDown, Sparkles } from '@/lib/icons'
import { cn } from '@/lib/utils'
import {
  DESKTOP_WORK_MODES,
  desktopWorkModeLabel,
  isDesktopWorkMode
} from '@/lib/work-modes'
import {
  $currentWorkMode,
  $freshDraftReady,
  $newChatWorkMode,
  setNewChatWorkMode
} from '@/store/session'

const PILL = cn(
  'h-(--composer-control-size) max-w-40 shrink-0 gap-1 rounded-md px-2 text-xs font-normal',
  'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
)

/**
 * New-chat-only capability chooser. Once a prompt creates a runtime session,
 * the selected mode remains visible but becomes read-only: work modes define
 * the agent's initial tool schema and must never be toggled mid-conversation.
 */
export function WorkModePill({ disabled }: { disabled: boolean }) {
  const freshDraftReady = useStore($freshDraftReady)
  const workMode = useStore($newChatWorkMode)
  const currentWorkMode = useStore($currentWorkMode)
  const [open, setOpen] = useState(false)

  if (!freshDraftReady) {
    if (!currentWorkMode) {
      return null
    }

    return (
      <span
        aria-label={`Work mode: ${desktopWorkModeLabel(currentWorkMode)}`}
        className="flex h-(--composer-control-size) max-w-40 shrink-0 items-center gap-1 px-2 text-xs text-(--ui-text-tertiary)"
        title="Work mode selected when this conversation started"
      >
        <Sparkles className="size-3 shrink-0" />
        <span className="truncate">{desktopWorkModeLabel(currentWorkMode)}</span>
      </span>
    )
  }

  const label = desktopWorkModeLabel(workMode)

  return (
    <DropdownMenu onOpenChange={setOpen} open={open}>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={`Work mode: ${label}`}
          className={PILL}
          disabled={disabled}
          title="Choose the capabilities for this new conversation"
          type="button"
          variant="ghost"
        >
          <Sparkles className="size-3 shrink-0" />
          <span className="truncate">{label}</span>
          <ChevronDown className="size-2.5 shrink-0 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-1" side="top" sideOffset={8}>
        <DropdownMenuLabel>Start a focused session</DropdownMenuLabel>
        <p className="px-2 pb-1 text-xs text-(--ui-text-tertiary)">
          This choice is fixed when the conversation starts.
        </p>
        <DropdownMenuRadioGroup
          onValueChange={value => {
            if (isDesktopWorkMode(value)) {
              setNewChatWorkMode(value)
              setOpen(false)
            }
          }}
          value={workMode}
        >
          {DESKTOP_WORK_MODES.map(mode => (
            <DropdownMenuRadioItem className="items-start py-2" key={mode.id} value={mode.id}>
              <span className="min-w-0">
                <span className="block text-xs font-medium text-foreground">{mode.label}</span>
                <span className="mt-0.5 block text-xs leading-snug text-(--ui-text-tertiary)">{mode.description}</span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
