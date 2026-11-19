import { fetchJson } from '../../lib/api'
import IntelWorkspace from './IntelWorkspace'
import '../terminal/terminal.css'

export default async function IntelPage() {
  const data = await fetchJson('/api/intel').catch(() => null)
  return <IntelWorkspace data={data} />
}
