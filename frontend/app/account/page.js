import { fetchJson } from '../../lib/api'
import AccountWorkspace from './AccountWorkspace'
import '../terminal/terminal.css'

export default async function AccountPage() {
  const [paper, security] = await Promise.allSettled([fetchJson('/api/paper'), fetchJson('/api/security/status')])
  const vault = security.status === 'fulfilled' ? security.value?.vault : null
  const session = paper.status === 'fulfilled' ? paper.value : null
  const summary = session ? {
    running: session.running, paused: session.paused, last_update: session.last_update,
    portfolio: session.portfolio, metrics: session.metrics,
  } : null
  return <AccountWorkspace paper={summary}
    vaultNames={vault ? (vault.secrets ?? []).map(secret => secret.name) : null} />
}
