import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

/**
 * Aucune ressource distante n'est autorisée : pas de CDN, pas de police
 * distante, pas de télémétrie. Le bundle est servi par le backend local.
 */
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    // Toutes les ressources sont intégrées au bundle local.
    assetsInlineLimit: 4096,
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8731',
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
  },
});
