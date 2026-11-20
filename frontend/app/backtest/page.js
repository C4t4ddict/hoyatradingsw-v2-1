import BacktestWorkspace from './BacktestWorkspace'
import '../terminal/terminal.css'

export const dynamic = 'force-dynamic'

export default function BacktestPage() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date())
  const { year, month, day } = Object.fromEntries(parts.map(part => [part.type, part.value]))
  const today = [year, month, day].join('-')
  const start = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day) - 179)).toISOString().slice(0, 10)
  return <BacktestWorkspace today={today} start={start} />
}
