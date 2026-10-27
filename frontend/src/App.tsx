import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Activity, AlertTriangle, BatteryCharging, BookOpen, BarChart3, CircleHelp, Play, Radio, RotateCcw, ShieldCheck, Square, Wifi, WifiOff, Zap } from 'lucide-react'

type Scenario = { id: string; title: string; description: string; level: string; story_steps: string[] }
type Frame = {
  t: number; truth: { temp: number; v: number; i: number; soc: number }; truth_undefended: { temp: number }
  reported: { temp: number }; predicted: { temp: number }; state: string
  evidence: { nis: number; nis_thr: number; cusum: Record<string, number>; cusum_thr: number; probe: { gain_v: number | null; gain_i: number | null; gain_min: number; active: boolean; failed: boolean } }
  control: { i_req: number; i_cmd: number; i_safe: number; mode: string }; margins: { temp: number; v: number }
  attack: { active: boolean; name: string; onset: number | null }; localization: { channel: string; confidence: number }
}
type WireMessage = { type: string; frames?: Frame[]; message?: string; kind?: string; text?: string; t?: number; result?: Record<string, number | boolean> }
type Benchmark = { detection_rate: number | null; detections: number; runs: number; median_delay_s: number | null; hazard_event_rate: number | null; false_alarms_per_hour: number | null; preempted_before_activation_runs: number }
type BenchmarkPayload = { results: { scenarios: Record<string, Record<string, Benchmark>> }; meta: { runtime_seconds: number; git_hash: string; config_hash: string; seeds: number[]; workers: number } }
type LimitsPayload = { threat_model: { protected_assets: string[]; attacker_capabilities: string[]; attacker_out_of_scope: string[] }; method: Record<string, string>; limitations: string[] }
const API = ''
const OFFLINE_SCENARIOS: Scenario[] = [
  { id: 'baseline', title: 'Honest charging', description: 'Attack-free charging with seeded sensor noise.', level: 'baseline', story_steps: ['Establish the honest charging trajectory and its noise floor.'] },
  { id: 'spike', title: 'Telemetry spikes', description: 'Brief temperature and voltage telemetry glitches.', level: 'A0', story_steps: ['Brief glitches test range checks and fast passive alarms.'] },
  { id: 'drift', title: 'Slow temperature drift', description: 'Reported temperature drifts down while the cell heats.', level: 'A1', story_steps: ['Gradual telemetry drift challenges cumulative detection.'] },
  { id: 'replay', title: 'Cooling fault with replay', description: 'Old telemetry is replayed while cooling degrades.', level: 'A1', story_steps: ['Replayed signals conceal a real cooling degradation.'] },
  { id: 'model_synthesis', title: 'Model-aware synthesis', description: 'A private twin forges plausible telemetry without probe knowledge.', level: 'A1', story_steps: ['A model-aware attacker forges coherent telemetry without probe knowledge.'] },
  { id: 'malicious_command', title: 'Malicious CV request', description: 'A valid-looking request overrides the charging taper.', level: 'A1', story_steps: ['A valid-looking request overrides the upstream CV taper.'] },
  { id: 'oracle_limit', title: 'Oracle attacker limit', description: 'An oracle attacker knows true actuator current.', level: 'A2', story_steps: ['An oracle attacker shows the explicit limit of telemetry-only defenses.'] },
]

function fmtTime(seconds: number) { const n = Math.max(0, Math.floor(seconds)); return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}` }
function format(value: number | null | undefined, digits = 1) { return value == null || !Number.isFinite(value) ? '—' : value.toFixed(digits) }

function Trace({ frames }: { frames: Frame[] }) {
  const width = 860, height = 260, pad = 24
  const values = frames.map((f) => f.truth.temp)
  const min = Math.min(20, ...values) - 1, max = Math.max(45, ...values) + 1
  const x = (i: number) => pad + i * (width - 2 * pad) / Math.max(1, frames.length - 1)
  const y = (v: number) => height - pad - (v - min) * (height - 2 * pad) / Math.max(1, max - min)
  const path = (pick: (f: Frame) => number) => frames.map((f, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(pick(f)).toFixed(1)}`).join(' ')
  const latest = frames[frames.length - 1]
  return <div className="trace-wrap" role="img" aria-label={`Temperature traces. Protected ${format(latest?.truth.temp)} degrees Celsius; unprotected ${format(latest?.truth_undefended.temp)} degrees Celsius.`}>
    <svg viewBox={`0 0 ${width} ${height}`} className="trace" preserveAspectRatio="none">
      {[25, 35, 45, 55].map((tick) => <g key={tick}><line x1={pad} x2={width - pad} y1={y(tick)} y2={y(tick)} className={tick === 55 ? 'grid limit' : 'grid'} /><text x={pad - 5} y={y(tick) - 5} textAnchor="end" className="axis-label">{tick}°</text></g>)}
      {frames.some((f) => f.attack.active) && <rect x={x(frames.findIndex((f) => f.attack.active))} y={pad} width={Math.max(1, width - pad - x(frames.findIndex((f) => f.attack.active)))} height={height - 2 * pad} className="attack-shade" />}
      <path d={path((f) => f.truth_undefended.temp)} className="line unprotected" />
      <path d={path((f) => f.reported.temp)} className="line reported" />
      <path d={path((f) => f.predicted.temp)} className="line predicted" />
      <path d={path((f) => f.truth.temp)} className="line protected" />
      {latest && <circle cx={x(frames.length - 1)} cy={y(latest.truth.temp)} r="4" className="point" />}
      <text x={pad} y={height - 4} className="axis-label">{fmtTime(frames[0]?.t ?? 0)}</text><text x={width - pad} y={height - 4} textAnchor="end" className="axis-label">{fmtTime(latest?.t ?? 0)}</text>
    </svg>
    <div className="trace-legend"><span><i className="key protected-key" />Protected plant</span><span><i className="key hazard-key" />Unprotected plant</span><span><i className="key dashed-key" />Reported</span><span><i className="key thin-key" />Twin estimate</span><span className="limit-key">55°C simulated limit</span></div>
  </div>
}

export default function App() {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [scenarioId, setScenarioId] = useState('model_synthesis')
  const [seed, setSeed] = useState(4242)
  const [speed, setSpeed] = useState(20)
  const [attackToInject, setAttackToInject] = useState('AT1')
  const [paused, setPaused] = useState(false)
  const [frames, setFrames] = useState<Frame[]>([])
  const [status, setStatus] = useState<'checking' | 'connected' | 'offline'>('checking')
  const [configHash, setConfigHash] = useState('')
  const [runStatus, setRunStatus] = useState('Ready')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [events, setEvents] = useState<string[]>([])
  const [error, setError] = useState('')
  const [view, setView] = useState('Console')
  const [replay, setReplay] = useState(false)
  const socket = useRef<WebSocket | null>(null)
  const frame = frames[frames.length - 1]
  const selected = scenarios.find((s) => s.id === scenarioId)

  const stop = useCallback(() => { socket.current?.close(); socket.current = null; setSessionId(null); setRunStatus('Paused') }, [])
  const start = useCallback(async (id = scenarioId, runSeed = seed) => {
    stop(); setError(''); setFrames([]); setEvents([]); setReplay(false); setRunStatus('Preparing simulation…')
    try {
      const response = await fetch(`${API}/api/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario_id: id, seed: runSeed, speed }) })
      if (!response.ok) throw new Error((await response.json()).error?.message ?? `Could not start run (${response.status})`)
      const { session_id: sid } = await response.json() as { session_id: string }
      setSessionId(sid); setRunStatus('Connecting to simulator…')
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${location.host}/api/sessions/${sid}/ws`); socket.current = ws
      ws.onopen = () => { setRunStatus('Live simulation'); setPaused(false) }
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data) as WireMessage
        if (data.type === 'frame_batch' && data.frames) { setFrames((old) => [...old, ...data.frames!].slice(-420)); setRunStatus('Live simulation') }
        else if (data.type === 'event') setEvents((old) => [`${data.text ?? data.kind} · ${fmtTime(data.t ?? 0)}`, ...old].slice(0, 8))
        else if (data.type === 'done') setRunStatus('Run complete')
        else if (data.type === 'error') { setError(data.message ?? 'Simulator reported an error'); setRunStatus('Run interrupted') }
      }
      ws.onerror = () => { setError('The simulator connection failed. Try the recorded replay below.'); setRunStatus('Connection lost') }
      ws.onclose = () => { if (socket.current === ws) { socket.current = null; setSessionId(null) } }
    } catch (cause) { setRunStatus('Unable to start'); setError(cause instanceof Error ? cause.message : 'Could not start the simulation.') }
  }, [scenarioId, seed, speed, stop])

  const loadReplay = useCallback(async () => {
    try {
      const response = await fetch(`/demo-runs/${scenarioId}.json`)
      if (!response.ok) throw new Error('No recorded run is available for this scenario yet.')
      const payload = await response.json() as { frames?: Frame[]; data?: Frame[] }
      const recorded = payload.frames ?? payload.data ?? []
      if (!recorded.length) throw new Error('The recorded run contains no frames.')
      stop(); setFrames(recorded); setReplay(true); setError(''); setRunStatus('Recorded replay'); setEvents(['Showing recorded simulation data'])
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Replay could not be loaded.') }
  }, [scenarioId, stop])

  useEffect(() => { let active = true; Promise.all([fetch('/api/health'), fetch('/api/scenarios')]).then(async ([healthResponse, scenariosResponse]) => { if (!healthResponse.ok || !scenariosResponse.ok) throw new Error('API unavailable'); return [await healthResponse.json(), await scenariosResponse.json()] as const }).then(([health, rows]: readonly [{ config_hash: string }, Scenario[]]) => { if (active) { setConfigHash(health.config_hash); setScenarios(rows); setStatus('connected') } }).catch(() => { if (active) { setScenarios(OFFLINE_SCENARIOS); setStatus('offline') } }); return () => { active = false } }, [])
  useEffect(() => () => { socket.current?.close() }, [])
  const chartFrames = useMemo(() => frames, [frames])
  const togglePause = () => { if (!socket.current || socket.current.readyState !== WebSocket.OPEN) return; const next = !paused; socket.current.send(JSON.stringify({ type: next ? 'pause' : 'resume' })); setPaused(next); setRunStatus(next ? 'Simulation paused' : 'Live simulation') }
  const changeSpeed = (value: number) => { setSpeed(value); if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: 'speed', value })) }
  const injectAttack = () => { if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: 'inject', attack: attackToInject })) }
  const operatorReset = () => { if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: 'operator_reset' })) }

  return <div className="app-shell">
      <aside className="rail"><div className="brand"><div className="brand-mark"><Activity size={19} /></div><span>PhysiGuard<small>SIMULATION LAB</small></span></div>
      <div className="rail-label">Workspace</div><nav aria-label="Main navigation">{[['Console', Radio], ['Lab', BatteryCharging], ['Benchmarks', BarChart3], ['Method', BookOpen]].map(([name, Icon]) => <button key={name as string} onClick={() => setView(name as string)} className={`nav-item ${view === name ? 'active' : ''}`}><Icon size={17} />{name as string}</button>)}</nav>
      <div className="rail-bottom"><div className="rail-label">RUN IDENTITY</div><strong>{sessionId?.slice(0, 8) ?? 'No active run'}</strong><span>Seed {seed}</span><button className="help-link" onClick={() => setView('Method')}><CircleHelp size={15} /> About this simulation</button></div>
    </aside>
    <main className="main-area"><header className="topbar"><div className="crumb">Project <b>/</b> {view}</div><div className="top-status"><span className={`connection-dot ${status}`} />{status === 'connected' ? 'Backend connected' : status === 'offline' ? 'Backend unavailable' : 'Connecting'}<span className="top-divider" /><span className="mono">CONFIG {configHash || '—'}</span></div></header>
      <div className="content"><div className="page-heading"><div><div className="eyebrow">CYBER-PHYSICAL INTEGRITY · SIMULATED</div><h1>{view === 'Console' ? 'Live console' : view}</h1><p>{view === 'Lab' ? 'Explore the attack ladder with reproducible, seeded runs.' : 'One attack. Two identical batteries. Watch the physical response diverge.'}</p></div><div className="heading-actions"><span className={`state-pill ${frame?.state === 'SAFE_MODE' ? 'safe' : frame?.state === 'CONFIRMED' ? 'danger' : ''}`}><span className="pill-dot" />{frame?.state?.replace('_', ' ') ?? 'READY'}</span><button className="icon-button" title="Reset run" onClick={() => void start()} disabled={status !== 'connected'}><RotateCcw size={16} /></button></div></div>
      {view === 'Benchmarks' ? <BenchmarksPage /> : view === 'Method' ? <MethodPage /> : <>
      {error && <div className="notice error-notice" role="alert"><AlertTriangle size={17} /><span>{error}</span><button onClick={() => void loadReplay()}>Load recorded replay</button></div>}
      {replay && <div className="notice replay-notice"><Radio size={16} /><strong>Recorded replay.</strong> This is not a live simulation.</div>}
      {!status || status === 'checking' ? null : status === 'offline' && !replay ? <div className="notice offline-notice"><WifiOff size={17} /> Simulator unavailable. You can still inspect a recorded run.<button onClick={() => void loadReplay()}>Load replay</button></div> : null}

      {view === 'Lab' && <section className="panel lab-panel"><div className="panel-head"><div><span className="eyebrow">GUIDED STORY · ATTACK LADDER</span><h2>Choose a reproducible scenario</h2></div><span className="subtle">Select a step to load it into the console</span></div><div className="story-list">{scenarios.map((item, index) => <button className={`story-step ${scenarioId === item.id ? 'selected' : ''}`} key={item.id} onClick={() => { setScenarioId(item.id); setView('Console') }}><span className="story-index">{String(index + 1).padStart(2, '0')}</span><span className="story-copy"><strong>{item.title}</strong><small>{item.story_steps[0] ?? item.description}</small></span><span className="story-level">{item.level}</span></button>)}</div></section>}

      <section className="run-summary"><div className="summary-main"><span className="summary-label">SCENARIO</span><strong>{selected?.title ?? 'Loading scenario…'}</strong><span>{selected?.description ?? 'Choose a reproducible simulation scenario.'}</span></div><div className="summary-cell"><span>SIM TIME</span><strong className="mono">{fmtTime(frame?.t ?? 0)}</strong></div><div className="summary-cell"><span>SEED</span><strong className="mono">{seed}</strong></div><div className="summary-cell"><span>CHANNEL</span><strong>{frame?.localization?.channel ?? '—'}</strong></div></section>

      <section className="data-grid"><div className="panel trace-panel"><div className="panel-head"><div><span className="eyebrow">PLANT RESPONSE</span><h2>Battery temperature</h2></div><span className="unit-tag">°C <i>· simulated</i></span></div>{chartFrames.length ? <Trace frames={chartFrames} /> : <div className="chart-empty"><div className="empty-icon"><Activity size={22} /></div><strong>Waiting for a simulation</strong><span>Start a run to compare protected and unprotected battery temperatures.</span></div>}</div>
      <aside className="panel event-panel"><div className="panel-head"><div><span className="eyebrow">OBSERVABILITY</span><h2>Run events</h2></div><span className="count-tag">{events.length.toString().padStart(2, '0')}</span></div><div className="event-list">{events.length ? events.map((event, i) => <div className="event-row" key={`${event}-${i}`}><span className="event-marker" /><span>{event}</span></div>) : <div className="quiet-empty">No events yet.<br />Detection and response events will appear here.</div>}</div><div className="event-foot"><ShieldCheck size={15} /> Events are generated by the simulation</div></aside></section>

      <section className="metric-grid"><Metric label="Protected temperature" value={format(frame?.truth.temp)} unit="°C" detail="True simulated plant state" color="blue" /><Metric label="Unprotected temperature" value={format(frame?.truth_undefended.temp)} unit="°C" detail="Paired counterfactual plant" color="red" /><Metric label="Hazard margin" value={format(frame?.margins.temp)} unit="°C" detail="To simulated temperature limit" color={frame && frame.margins.temp < 5 ? 'red' : 'green'} /><Metric label="Charging current" value={format(frame?.control.i_cmd)} unit="A" detail={`Request ${format(frame?.control.i_req)} A · ${frame?.control.mode ?? '—'}`} color="neutral" /></section>

      <section className="lower-grid"><div className="panel evidence-panel"><div className="panel-head"><div><span className="eyebrow">DETECTION EVIDENCE</span><h2>Signals and trust</h2></div><span className="subtle">Live from the twin and detectors</span></div><div className="evidence-items"><Evidence label="NIS score" value={format(frame?.evidence.nis, 2)} threshold={format(frame?.evidence.nis_thr, 2)} /><Evidence label="Temperature CUSUM" value={format(frame?.evidence.cusum.temp, 2)} threshold={format(frame?.evidence.cusum_thr, 2)} /><Evidence label="Probe gain" value={format(frame?.evidence.probe.gain_v, 2)} threshold={format(frame?.evidence.probe.gain_min, 2)} /></div></div><div className="panel control-panel"><div className="panel-head"><div><span className="eyebrow">OPERATOR CONTROLS</span><h2>Simulation controls</h2></div><Zap size={17} className="control-icon" /></div><div className="controls"><label>Scenario<select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>{scenarios.map((s) => <option value={s.id} key={s.id}>{s.title}</option>)}</select></label><label>Seed<input type="number" min="0" max="4294967295" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></label><label>Playback speed<select value={speed} onChange={(e) => changeSpeed(Number(e.target.value))}><option value={1}>1×</option><option value={5}>5×</option><option value={20}>20×</option><option value={60}>60×</option></select></label><div className="button-row"><button className="primary-button" onClick={() => void start()} disabled={status !== 'connected' || runStatus.includes('Preparing')}><Play size={15} fill="currentColor" /> Start run</button><button className="secondary-button" onClick={togglePause} disabled={!sessionId}>{paused ? <Play size={14} /> : <Square size={14} />} {paused ? 'Resume' : 'Pause'}</button><button className="secondary-button" onClick={() => void loadReplay()}><Wifi size={14} /> Replay</button>{frame?.state === 'SAFE_MODE' && <button className="secondary-button" onClick={operatorReset} disabled={!sessionId}>Reset to normal</button>}</div><div className="inject-row"><label>Attack injection<select value={attackToInject} onChange={(e) => setAttackToInject(e.target.value)}>{['AT1','AT2','AT3','AT4','AT5','AT6'].map((attack) => <option key={attack}>{attack}</option>)}</select></label><button className="secondary-button" onClick={injectAttack} disabled={!sessionId}>Inject attack</button></div><span className="run-status">{runStatus}</span></div></div></section>
      <footer>PhysiGuard is a simulated research prototype. Results do not establish real-cell safety or deployment readiness.<span><span className="footer-dot" />{status === 'connected' ? 'API available' : 'Offline-capable'}</span></footer>
      </>}
      </div>
    </main>
  </div>
}

function Metric({ label, value, unit, detail, color }: { label: string; value: string; unit: string; detail: string; color: string }) { return <article className="metric"><span className="metric-label">{label}</span><div className={`metric-value ${color}`}>{value}<small>{unit}</small></div><span className="metric-detail">{detail}</span></article> }
function Evidence({ label, value, threshold }: { label: string; value: string; threshold: string }) { return <div className="evidence"><span>{label}</span><strong className="mono">{value}</strong><small>limit <span className="mono">{threshold}</span></small><div className="evidence-track"><i /></div></div> }

function BenchmarksPage() {
  const [payload, setPayload] = useState<BenchmarkPayload | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { let live = true; fetch('/api/benchmarks').then(async (response) => { if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(body?.error?.message ?? 'Benchmark results are unavailable.') } return response.json() as Promise<BenchmarkPayload> }).then((data) => { if (live) setPayload(data) }).catch((cause: unknown) => { if (live) setError(cause instanceof Error ? cause.message : 'Benchmark results could not be loaded.') }); return () => { live = false } }, [])
  if (error) return <div className="panel data-page empty-page"><AlertTriangle size={20} /><h2>Benchmark results unavailable</h2><p>{error}</p><code>Run the P7 evaluation, then reload this view.</code></div>
  if (!payload) return <div className="panel data-page empty-page"><Activity size={20} /><h2>Loading evaluation results</h2><p>Reading the committed benchmark artifacts from the API.</p></div>
  const scenarios = Object.entries(payload.results.scenarios)
  const detectors = ['B0', 'B1', 'B2', 'B3']
  return <div className="benchmark-page"><section className="metric-grid benchmark-summary"><Metric label="Evaluation runtime" value={format(payload.meta.runtime_seconds / 60, 1)} unit="min" detail="Full 1,400-run P7 evaluation" color={payload.meta.runtime_seconds < 600 ? 'green' : 'red'} /><Metric label="Held-out seeds" value={String(payload.meta.seeds.length)} unit="runs" detail={`${payload.meta.seeds[0]}–${payload.meta.seeds[payload.meta.seeds.length - 1]}`} color="blue" /><Metric label="B3 false alarms" value={format(scenarios.reduce((sum, [, row]) => sum + (row.B3?.false_alarms_per_hour ?? 0), 0) / Math.max(1, scenarios.length), 2)} unit="/h avg" detail="Reported across scenario rows" color="red" /><Metric label="Worker count" value={String(payload.meta.workers)} unit="workers" detail="Recorded in evaluation metadata" color="neutral" /></section>
    <section className="panel benchmark-table-panel"><div className="panel-head"><div><span className="eyebrow">TEST SPLIT · 3,600 S PER RUN</span><h2>Detector outcomes by attack</h2></div><span className="subtle">Failures remain visible with the same weight</span></div><div className="table-scroll"><table className="benchmark-table"><thead><tr><th>Attack</th>{detectors.map((key) => <th key={key}>{key}<small>{key === 'B0' ? 'Range' : key === 'B1' ? 'EKF' : key === 'B2' ? 'Active' : 'Full'}</small></th>)}</tr></thead><tbody>{scenarios.map(([attack, row]) => <tr key={attack}><th scope="row">{attack === 'baseline' ? 'Attack-free' : attack}</th>{detectors.map((key) => { const value = row[key]; return <td key={key} className={value?.detection_rate === 0 || (value?.false_alarms_per_hour ?? 0) > 0.2 ? 'table-failure' : ''}><strong>{value?.detection_rate == null ? 'N/A' : `${format(value.detection_rate * 100, 0)}%`}</strong><small>{value?.detections ?? 0}/{value?.runs ?? '—'} detected</small><small>delay {value?.median_delay_s == null ? 'N/A' : `${format(value.median_delay_s, 0)} s`}</small><small>{format(value?.false_alarms_per_hour, 2)} false alarms/h</small><small>{format(value?.hazard_event_rate == null ? null : value.hazard_event_rate * 100, 0)}% hazard events</small>{value?.preempted_before_activation_runs ? <small>{value.preempted_before_activation_runs} preempted</small> : null}</td> })}</tr>)}</tbody></table></div></section>
    <div className="panel metadata-panel"><div><span className="eyebrow">PROVENANCE</span><h2>Evaluation metadata</h2></div><dl><div><dt>Code revision</dt><dd className="mono">{payload.meta.git_hash.slice(0, 12)}</dd></div><div><dt>Configuration</dt><dd className="mono">{payload.meta.config_hash}</dd></div><div><dt>Seeds</dt><dd className="mono">{payload.meta.seeds[0]}–{payload.meta.seeds[payload.meta.seeds.length - 1]}</dd></div></dl><p className="honest-note"><AlertTriangle size={15} /> These are simulation results. The recorded full evaluation took {format(payload.meta.runtime_seconds / 60, 1)} minutes; the P7 runtime target is 10 minutes.</p></div>
  </div>
}

function MethodPage() {
  const [data, setData] = useState<LimitsPayload | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { let live = true; fetch('/api/limits').then((response) => { if (!response.ok) throw new Error('Method and limitations are temporarily unavailable.'); return response.json() as Promise<LimitsPayload> }).then((payload) => { if (live) setData(payload) }).catch((cause: unknown) => { if (live) setError(cause instanceof Error ? cause.message : 'Could not load method details.') }); return () => { live = false } }, [])
  if (error || !data) return <div className="panel data-page empty-page"><BookOpen size={20} /><h2>{error ? 'Method view unavailable' : 'Loading method and limits'}</h2><p>{error || 'Loading the API threat model and declared limitations.'}</p></div>
  return <div className="method-page"><section className="panel method-intro"><span className="eyebrow">SYSTEM MODEL</span><h2>A digital twin checks whether telemetry matches physics.</h2><p>Two identical simulated battery plants receive the same attack. The protected path estimates state, accumulates evidence, tests telemetry with keyed current probes, and constrains unsafe charging requests.</p><div className="architecture"><span>Battery plant</span><i>→</i><span>Telemetry + attacker</span><i>→</i><span>Digital twin</span><i>→</i><span>Detection and response</span></div></section><div className="method-columns"><section className="panel method-list"><div className="panel-head"><div><span className="eyebrow">METHOD</span><h2>Implemented stages</h2></div></div>{Object.entries(data.method).map(([key, value]) => <div className="method-row" key={key}><strong>{key.replace(/_/g, ' ')}</strong><span>{value}</span></div>)}</section><section className="panel method-list"><div className="panel-head"><div><span className="eyebrow">THREAT MODEL</span><h2>Scope and limits</h2></div></div><h3>Protected assets</h3><TagList items={data.threat_model.protected_assets} /><h3>Attacker capabilities</h3><TagList items={data.threat_model.attacker_capabilities} /><h3>Out of scope</h3><TagList items={data.threat_model.attacker_out_of_scope} /><h3>Limitations</h3><ul className="limitations">{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section></div><p className="honest-note"><AlertTriangle size={15} /> This is a simulated prototype. It is not real-cell validation, certification, or deployment evidence.</p></div>
}

function TagList({ items }: { items: string[] }) { return <ul className="tag-list">{items.map((item) => <li key={item}>{item}</li>)}</ul> }
