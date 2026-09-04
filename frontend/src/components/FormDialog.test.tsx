/**
 * 入力ダイアログ（ADR-0027）の閉じ方。
 *
 * 見るのは「閉じる操作がすべて呼び出し側へ伝わること」。`<dialog>` の既定では、
 * Esc はダイアログだけを閉じて呼び出し側の状態が開いたまま残り、次に「追加」を
 * 押しても何も出なくなる。
 *
 * 幅による見え方（狭い画面で下から幅いっぱい）は CSS が決めるため、jsdom では
 * 検証できない（ADR-0011）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import { FormDialog } from './FormDialog'

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function renderDialog(onClose: () => void) {
  return render(
    <I18nProvider settings={SETTINGS}>
      <FormDialog title="Add user" onClose={onClose}>
        <form className="dialog-form">
          <p>form contents</p>
          <input aria-label="Name" />
        </form>
      </FormDialog>
    </I18nProvider>,
  )
}

describe('FormDialog', () => {
  it('見出しと中身を出す', () => {
    renderDialog(vi.fn())

    expect(screen.getByRole('heading', { name: 'Add user' })).toBeInTheDocument()
    expect(screen.getByText('form contents')).toBeInTheDocument()
  })

  it('開いたら最初の入力欄へフォーカスが入る（閉じるボタンではなく）', () => {
    renderDialog(vi.fn())

    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveFocus()
  })

  it('✕ で閉じる', () => {
    const onClose = vi.fn()
    renderDialog(onClose)

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Esc（cancel）でも閉じる。ブラウザ既定の取り消しは止める', () => {
    const onClose = vi.fn()
    const { container } = renderDialog(onClose)
    const dialog = container.querySelector('dialog')
    expect(dialog).not.toBeNull()

    const cancel = new Event('cancel', { bubbles: false, cancelable: true })
    fireEvent(dialog as HTMLDialogElement, cancel)

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(cancel.defaultPrevented).toBe(true)
  })
})
