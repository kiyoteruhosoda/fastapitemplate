import { useEffect, useState } from 'react'

interface Info {
  version: string
  git_sha: string
}

export function Footer() {
  const [info, setInfo] = useState<Info | null>(null)

  useEffect(() => {
    fetch('/info')
      .then((r) => (r.ok ? r.json() : null))
      .then(setInfo)
      .catch(() => {
        setInfo(null)
      })
  }, [])

  // Note: **no `v` prefix.** The version is a short commit hash, not a meaningful version
  //   number. The server-side value has none either, so adding one here gives `vv11eeceb`.
  // Note: **do not append git_sha in parentheses.** Now that the version is the short commit
  //   hash, it would just repeat the same value (`47fbe59 (47fbe59)`). Branch builds put the
  //   branch name in the version, so the version alone is enough.
  return <footer className="footer">{info ? info.version : ''}</footer>
}
