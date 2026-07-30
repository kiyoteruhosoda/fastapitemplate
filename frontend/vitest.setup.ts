import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// テスト間で DOM を持ち越さない（describe をまたいだ副作用を防ぐ）
afterEach(() => {
  cleanup()
})
