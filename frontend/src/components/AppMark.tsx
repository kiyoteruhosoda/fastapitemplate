/**
 * App mark (shown in the header and the heading of the pre-sign-in screens).
 *
 * Has no artwork of its own; it loads the same `favicon.svg` as the tab icon. The single
 * source is `scripts/generate_pwa_icons.py`, so changing the design or colors changes the
 * tab icon, the home screen icon and this mark together. Places that need the mark should
 * use this component instead of redrawing it.
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
