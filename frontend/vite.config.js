import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Detect environment
// Replit sets REPL_ID; PORT is the frontend port Replit assigns (default 5000)
const isReplit = !!process.env.REPL_ID
const frontendPort = isReplit ? (parseInt(process.env.PORT) || 5000) : 3000
const backendPort  = isReplit ? 8000 : 8001
const backendHost  = isReplit ? '0.0.0.0' : '127.0.0.1'

export default defineConfig({
  plugins: [react()],
  server: {
    port: frontendPort,
    host: isReplit ? '0.0.0.0' : '127.0.0.1',  // Replit needs 0.0.0.0 to expose the port
    strictPort: true,
    allowedHosts: isReplit ? 'all' : undefined,
    proxy: {
      '/api': {
        target: `http://${backendHost}:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
})
