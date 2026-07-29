import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'fastapitemplate',
        short_name: 'fastapitemplate',
        description: 'FastAPI + React application template',
        lang: 'ja',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        theme_color: '#4f46e5',
        background_color: '#ffffff',
        icons: [
          { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // SPA のシェル（ビルド成果物）だけを precache する。API・自動生成ドキュメント・
        // 運用エンドポイントはナビゲーションフォールバックの対象外にし、SW が
        // index.html を返して JSON 応答を壊さないようにする。
        globPatterns: ['**/*.{js,css,html,svg,png,ico,json}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [
          /^\/api\//,
          /^\/docs/,
          /^\/redoc/,
          /^\/openapi\.json/,
          /^\/metrics/,
          /^\/healthz/,
        ],
        // API 応答は SW でキャッシュしない（常にネットワークへ）。オフライン時は
        // フロント側のエラーハンドリング（i18n エラーコード変換）に委ねる。
        runtimeCaching: [],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      // 開発時はバックエンド（uv run python main.py）へプロキシする
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
