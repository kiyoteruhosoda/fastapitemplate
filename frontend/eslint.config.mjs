import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import sonarjs from 'eslint-plugin-sonarjs'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  // ビルド成果物・依存は解析対象外
  {
    // public/ はビルドを通らずそのまま配る素の JavaScript（Service Worker に読ませる
    // push-sw.js など）。型付きの解析の対象にできない。
    ignores: [
      'dist/**',
      'coverage/**',
      'dev-dist/**',
      'node_modules/**',
      'public/**',
      'playwright-report/**',
      'test-results/**',
    ],
  },

  js.configs.recommended,

  ...tseslint.configs.strictTypeChecked,

  {
    plugins: {
      'react-hooks': reactHooks,
      sonarjs,
    },

    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },

    rules: {
      '@typescript-eslint/no-floating-promises': 'error',

      '@typescript-eslint/no-explicit-any': 'error',

      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
        },
      ],

      '@typescript-eslint/consistent-type-imports': 'error',

      'react-hooks/rules-of-hooks': 'error',

      'react-hooks/exhaustive-deps': 'error',

      'sonarjs/cognitive-complexity': ['error', 15],

      // 数値の文字列化は一意で安全（ID を URL に埋める用途）。
      // このルールの主眼はオブジェクト・null の混入検出にある。
      '@typescript-eslint/restrict-template-expressions': [
        'error',
        {
          allowNumber: true,
        },
      ],
    },
  },

  // 時刻を文字にするのは services/localTime.ts だけ（ADR-0105）。ほかで書くと時間帯
  // （`UTC+9`）を付け忘れ、コピーした時刻がどの時計の時刻か分からなくなる。
  // 試験は期待値を作るために使ってよい。
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/services/localTime.ts', 'src/**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: 'CallExpression[callee.property.name=/^toLocale(String|TimeString)$/]',
          message:
            '時刻は services/localTime.ts の formatWithLocalZone などで文字にする（時間帯を付けるため。ADR-0105）。数値なら Intl.NumberFormat を使う。',
        },
        {
          selector:
            ':matches(NewExpression, CallExpression)[callee.object.name="Intl"][callee.property.name="DateTimeFormat"]',
          message:
            '時刻は services/localTime.ts の formatWithLocalZone などで文字にする（時間帯を付けるため。ADR-0105）。',
        },
      ],
    },
  },

  // 設定ファイル（Node 側）は型情報付き解析の対象外
  {
    files: ['*.config.{ts,mts,mjs}', 'eslint.config.mjs'],
    extends: [tseslint.configs.disableTypeChecked],
  },
)
