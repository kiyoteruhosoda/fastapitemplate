/**
 * パスワード欄の表示・非表示の切り替え。
 *
 * 検証するのは「既定は伏せ字」「押すと平文になり、もう一度押すと戻る」「入力値は
 * 切り替えで失われない」の 3 点。見た目（枠線）は CSS が担うのでここでは見ない。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'

import { I18nProvider } from '../i18n'
import type { UiSettings } from '../services/uiSettings'
import { PasswordInput } from './PasswordInput'

const SETTINGS: UiSettings = {
  languages: ['en'],
  default_locale: 'en',
  default_theme: 'light',
}

function renderInput(props: ComponentProps<typeof PasswordInput> = {}) {
  return render(
    <I18nProvider settings={SETTINGS}>
      <label>
        Password
        <PasswordInput {...props} />
      </label>
    </I18nProvider>,
  )
}

function field() {
  return screen.getByLabelText('Password')
}

describe('PasswordInput', () => {
  it('既定では伏せ字で表示する', () => {
    renderInput()
    expect(field()).toHaveAttribute('type', 'password')
    expect(screen.getByRole('button', { name: 'Show password' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('ボタンを押すと平文になり、もう一度押すと伏せ字へ戻る', () => {
    renderInput()

    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(field()).toHaveAttribute('type', 'text')

    const hide = screen.getByRole('button', { name: 'Hide password' })
    expect(hide).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(hide)
    expect(field()).toHaveAttribute('type', 'password')
  })

  it('切り替えても入力値は残る', () => {
    renderInput()

    fireEvent.change(field(), { target: { value: 'correct horse' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(field()).toHaveValue('correct horse')
  })

  it('入力欄が無効なら切り替えボタンも押せない', () => {
    renderInput({ disabled: true })
    expect(screen.getByRole('button', { name: 'Show password' })).toBeDisabled()
  })
})
