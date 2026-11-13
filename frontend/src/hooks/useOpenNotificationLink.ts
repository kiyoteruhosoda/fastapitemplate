/**
 * Open a notice's destination. In-app paths (`/items`) switch the screen; others open in a new tab.
 */
import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

import { isInAppLink } from '../services/notifications'

export function useOpenNotificationLink(): (link: string | null) => void {
  const navigate = useNavigate()
  return useCallback(
    (link: string | null) => {
      if (!link) return
      if (isInAppLink(link)) {
        void navigate(link)
        return
      }
      window.open(link, '_blank', 'noopener,noreferrer')
    },
    [navigate],
  )
}
