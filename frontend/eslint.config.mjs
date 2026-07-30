import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import sonarjs from 'eslint-plugin-sonarjs'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  // ビルド成果物・依存は解析対象外
  {
    ignores: ['dist/**', 'coverage/**', 'dev-dist/**', 'node_modules/**'],
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

  // 設定ファイル（Node 側）は型情報付き解析の対象外
  {
    files: ['*.config.{ts,mts,mjs}', 'eslint.config.mjs'],
    extends: [tseslint.configs.disableTypeChecked],
  },
)
