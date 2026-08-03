/**
 * ログ一覧（システムログ・監査ログ）の取得。
 *
 * 条件かページが変わるたびに取り直す。取得中は `searching` が真になり、検索ボタンに
 * 実行中の目印を出せる（ADR-0022）。条件が変わらなければ取りに行かないので、押しても
 * 結果が変わらない検索でスピナーが出たままにはならない。
 */
import { useEffect, useState } from 'react'

import { api } from '../services/api'
import { buildLogQuery, type LogFilters, type LogSearchResult } from '../services/logSearch'

export function useLogSearch<E>(
  path: string,
  filters: LogFilters,
  page: number,
): { result: LogSearchResult<E>; searching: boolean } {
  const [result, setResult] = useState<LogSearchResult<E>>({ total: 0, entries: [] })
  const [searching, setSearching] = useState(true)

  useEffect(() => {
    // 続けて条件が変わったとき、古い応答で新しい結果を上書きしない。
    let current = true
    setSearching(true)
    void api
      .get<LogSearchResult<E>>(`${path}${buildLogQuery(filters, page)}`)
      .then((data) => {
        if (current) setResult(data)
      })
      .finally(() => {
        if (current) setSearching(false)
      })
    return () => {
      current = false
    }
  }, [path, filters, page])

  return { result, searching }
}
