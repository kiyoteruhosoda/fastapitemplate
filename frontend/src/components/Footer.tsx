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

  return <footer className="footer">{info ? `v${info.version} (${info.git_sha})` : ''}</footer>
}
