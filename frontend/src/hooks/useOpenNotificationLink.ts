/**
 * お知らせの行き先を開く。アプリの中（`/items`）は画面の切り替えで、外は別のタブで開く。
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
        navigate(link)
        return
      }
      window.open(link, '_blank', 'noopener,noreferrer')
    },
    [navigate],
  )
}
