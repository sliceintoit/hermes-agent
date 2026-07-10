const DESKTOP_FILE_LINK_ORIGIN = 'https://desktop-file.hermes.invalid'
const DESKTOP_FILE_LINK_PATH = '/open'

function parseFileUrl(value: string): URL | null {
  try {
    const url = new URL(value)

    return url.protocol === 'file:' ? url : null
  } catch {
    return null
  }
}

/**
 * Converts a file URL into an HTTPS sentinel that survives Streamdown's
 * sanitize + harden pipeline. The main process remains responsible for path
 * scope validation when the decoded URL is opened.
 */
export function encodeDesktopFileLink(value: string): string {
  const fileUrl = parseFileUrl(value)

  if (!fileUrl) {
    return value
  }

  const sentinel = new URL(DESKTOP_FILE_LINK_PATH, DESKTOP_FILE_LINK_ORIGIN)

  sentinel.searchParams.set('target', fileUrl.href)

  return sentinel.href
}

/** Decode only our exact sentinel origin/path, and only back to file URLs. */
export function decodeDesktopFileLink(value?: string): string | null {
  if (!value) {
    return null
  }

  try {
    const sentinel = new URL(value)

    if (sentinel.origin !== DESKTOP_FILE_LINK_ORIGIN || sentinel.pathname !== DESKTOP_FILE_LINK_PATH) {
      return null
    }

    const target = sentinel.searchParams.get('target') || ''

    return parseFileUrl(target)?.href ?? null
  } catch {
    return null
  }
}

interface MarkdownNode {
  children?: MarkdownNode[]
  type?: string
  url?: string
}

/** Remark plugin: protect markdown file-link destinations before rehype hardening. */
export function remarkDesktopFileLinks() {
  return (tree: MarkdownNode) => {
    const visit = (node: MarkdownNode) => {
      if (node.type === 'link' && typeof node.url === 'string') {
        node.url = encodeDesktopFileLink(node.url)
      }

      node.children?.forEach(visit)
    }

    visit(tree)
  }
}
