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
      // Backend runs HTTPS (self-signed dev cert) so :3099 is also directly
      // reachable per the dev.ecoworks.ca convention; secure:false lets the
      // proxy trust that cert.
      '/api': {
        target: 'https://localhost:3099',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
