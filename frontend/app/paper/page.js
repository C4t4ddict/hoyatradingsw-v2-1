import { fetchJson } from '../../lib/api'
import PaperWorkspace from './PaperWorkspace'
import '../terminal/terminal.css'

export default async function PaperPage() {
  const [paper, runtime] = await Promise.allSettled([fetchJson('/api/paper'), fetchJson('/api/runtime')])
  return <PaperWorkspace initialPaper={paper.status === 'fulfilled' ? paper.value : null}
    initialSignals={runtime.status === 'fulfilled' ? runtime.value.signals : null} />
}
