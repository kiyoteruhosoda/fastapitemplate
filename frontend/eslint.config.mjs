import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import sonarjs from 'eslint-plugin-sonarjs'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  // Build output and dependencies are not linted
  {
    // public/ is plain JavaScript served as is without the build (e.g. push-sw.js loaded by
    // the Service Worker). It can't be type-aware linted.
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

      // Stringifying numbers is unambiguous and safe (used to embed IDs in URLs).
      // The rule is mainly about catching objects or null slipping in.
      '@typescript-eslint/restrict-template-expressions': [
        'error',
        {
          allowNumber: true,
        },
      ],
    },
  },

  // Only services/localTime.ts formats times as text (ADR-0105). Doing it elsewhere forgets the
  // offset (`UTC+9`), and copied times no longer say which clock they belong to.
  // Tests may use these to build expected values.
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/services/localTime.ts', 'src/**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: 'CallExpression[callee.property.name=/^toLocale(String|TimeString)$/]',
          message:
            'Format times with formatWithLocalZone etc. in services/localTime.ts (to include the offset; ADR-0105). For numbers, use Intl.NumberFormat.',
        },
        {
          selector:
            ':matches(NewExpression, CallExpression)[callee.object.name="Intl"][callee.property.name="DateTimeFormat"]',
          message:
            'Format times with formatWithLocalZone etc. in services/localTime.ts (to include the offset; ADR-0105).',
        },
      ],
    },
  },

  // Config files (Node side) are excluded from type-aware linting
  {
    files: ['*.config.{ts,mts,mjs}', 'eslint.config.mjs'],
    extends: [tseslint.configs.disableTypeChecked],
  },
)
