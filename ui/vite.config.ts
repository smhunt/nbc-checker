import { readFileSync, existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const certDir = resolve(homedir(), 'Code/.traefik/certs')
const certPath = resolve(certDir, 'cert.pem')
const keyPath = resolve(certDir, 'key.pem')
const https =
  existsSync(certPath) && existsSync(keyPath)
    ? { cert: readFileSync(certPath), key: readFileSync(keyPath) }
    : undefined

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3029,
    strictPort: true,
    host: true,
    https,
    proxy: {
      // Backend runs plain HTTP behind Traefik (TLS terminated at
      // https://nbc.dev.ecoworks.ca). The dev proxy targets it directly.
      '/api': {
        target: 'http://localhost:3099',
        changeOrigin: true,
      },
    },
  },
})
