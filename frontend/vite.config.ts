import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import packageJson from './package.json' with { type: 'json' }

export default defineConfig({
  plugins: [react()],
  define: { __ANYA_VERSION__: JSON.stringify(packageJson.version) },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'] },
})
