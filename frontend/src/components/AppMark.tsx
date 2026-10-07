/**
 * アプリの像（ヘッダー・サインイン前の画面の見出しに出す）。
 *
 * 絵は持たず、タブのアイコンと同じ `favicon.svg` をそのまま読む。正本は
 * `scripts/generate_pwa_icons.py` の 1 本だけで、図柄や色を変えるとタブ・
 * ホーム画面のアイコンとこの像がいっしょに変わる。像を足す場所でも絵を
 * 書き起こさず、この部品を使う。
 */
export function AppMark({ size }: { size: number }) {
  return (
    <img
      className="app-mark"
      src={`${import.meta.env.BASE_URL}favicon.svg`}
      width={size}
      height={size}
      alt=""
    />
  )
}
