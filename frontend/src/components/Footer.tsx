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

  // ⚠ **`v` を付けない。** 版はコミットの短縮ハッシュで、意味のある版数ではない。
  //   サーバ側の値にも付けていないので、ここで足すと `vv11eeceb` と二重になる。
  // ⚠ **git_sha を括弧で添えない。** 版がコミットの短縮ハッシュになった以上、
  //   同じ値が 2 回並ぶだけ（`47fbe59 (47fbe59)`）。枝で焼いたときは版のほうに
  //   枝の名前が付くので、出すなら版 1 つでよい。
  return <footer className="footer">{info ? info.version : ''}</footer>
}
