/**
 * Landing page - the front door for someone who has never seen this before.
 *
 * The hero is a live demo rather than a headline. On load the page invokes a
 * real function on the real fleet twice: the first call pays a cold start, the
 * second reuses the warm container. The milliseconds shown are measured, not
 * copy. The platform demonstrating itself is more convincing than any claim
 * about it, and it fails honestly -- if the backend is down or the demo
 * function is missing, the panel says so instead of showing invented numbers.
 *
 * Colour is semantic here: cobalt means cold start, amber means warm hit, and
 * those two values are the entire point of the architecture.
 */
import { useEffect, useState } from "react"
import { Link } from "react-router"
import { apiFetch, type ClusterResponse, type InvokeResponse } from "@/lib/api"

const DEMO_FUNCTION_ID = "demo-fib"

type Measurement = {
  ms: number
  cold: boolean
  worker: string
}

type DemoState =
  | { status: "running" }
  | { status: "done"; first: Measurement; second: Measurement }
  | { status: "unavailable"; reason: string }

async function invokeOnce(): Promise<Measurement> {
  const result = await apiFetch<InvokeResponse>(
    `/api/invoke/${DEMO_FUNCTION_ID}`,
    { method: "POST", body: JSON.stringify({ input: { n: 120 } }) }
  )
  if (!result.success) throw new Error(result.error || "Invocation failed")
  return {
    ms: result.duration_ms,
    cold: Boolean(result.cold_start),
    worker: result.worker_id || "unknown",
  }
}

export function Landing() {
  const [demo, setDemo] = useState<DemoState>({ status: "running" })
  const [cluster, setCluster] = useState<ClusterResponse | null>(null)

  useEffect(() => {
    let cancelled = false

    apiFetch<ClusterResponse>("/api/cluster")
      .then((data) => !cancelled && setCluster(data))
      .catch(() => {})

    // Sequential, not parallel: the second call has to find the container the
    // first one left warm, and two at once would each cold-start.
    ;(async () => {
      try {
        const first = await invokeOnce()
        const second = await invokeOnce()
        if (!cancelled) setDemo({ status: "done", first, second })
      } catch (err) {
        if (!cancelled) {
          setDemo({
            status: "unavailable",
            reason: err instanceof Error ? err.message : "Backend unreachable",
          })
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  const speedup =
    demo.status === "done" && demo.second.ms > 0
      ? Math.round((demo.first.ms / demo.second.ms) * 10) / 10
      : null

  const workers = cluster?.workers ?? []
  const ranOn = demo.status === "done" ? demo.second.worker : null

  return (
    <div className="lp">
      <style>{CSS}</style>

      <header className="lp-bar">
        <span className="lp-mark">Clowdy</span>
        <nav className="lp-nav">
          <Link to="/dashboard">Open the dashboard</Link>
          <a
            href="https://github.com/islamborghini/clowdy"
            target="_blank"
            rel="noreferrer"
          >
            Source
          </a>
        </nav>
      </header>

      <main>
        <section className="lp-hero">
          <div className="lp-hero-copy">
            <h1>Serverless, with the lid off.</h1>
            <p className="lp-lede">
              Clowdy runs Python functions in containers spread across a fleet of
              worker machines. It is a working rebuild of the parts of AWS Lambda
              that are actually interesting: keeping containers warm, and deciding
              which machine your code lands on.
            </p>
            <p className="lp-lede">
              This page is talking to a real deployment. It just called a function
              twice.
            </p>
          </div>

          <div className="lp-measure">
            {demo.status === "running" && (
              <p className="lp-measure-pending">Calling a function twice...</p>
            )}

            {demo.status === "unavailable" && (
              <div className="lp-measure-pending">
                <p>The fleet is not answering right now.</p>
                <p className="lp-fineprint">{demo.reason}</p>
              </div>
            )}

            {demo.status === "done" && (
              <>
                <div
                  className={
                    demo.first.cold
                      ? "lp-reading lp-reading--cold"
                      : "lp-reading lp-reading--warm"
                  }
                >
                  <span className="lp-reading-label">First call</span>
                  <span className="lp-reading-value">
                    {demo.first.ms}
                    <span className="lp-unit">ms</span>
                  </span>
                  <span className="lp-reading-note">
                    {demo.first.cold
                      ? "No container existed. One was created for it."
                      : "A container was already warm from an earlier visit."}
                  </span>
                </div>

                <div className="lp-reading lp-reading--warm">
                  <span className="lp-reading-label">Second call</span>
                  <span className="lp-reading-value">
                    {demo.second.ms}
                    <span className="lp-unit">ms</span>
                  </span>
                  <span className="lp-reading-note">
                    Reused the container the first call left behind.
                  </span>
                </div>

                {demo.first.cold ? (
                  <p className="lp-fineprint">
                    {speedup}x faster, on worker{" "}
                    <code>{demo.second.worker.slice(0, 12)}</code>. That gap is
                    what the scheduler exists to protect.
                  </p>
                ) : (
                  <p className="lp-fineprint">
                    Both calls were warm, on worker{" "}
                    <code>{demo.second.worker.slice(0, 12)}</code>. Containers are
                    reaped after five idle minutes, so come back later and the
                    first call pays the cold start again.
                  </p>
                )}
              </>
            )}
          </div>
        </section>

        <section className="lp-fleet">
          <div className="lp-fleet-copy">
            <h2>Your call had to land somewhere</h2>
            <p>
              Every worker keeps its own pool of warm containers. Send the same
              function to a different machine and you pay the cold start again,
              so spreading requests evenly is the wrong thing to do.
            </p>
            <p>
              Clowdy hashes the container image onto a ring and sends the call to
              the worker that already has it warm. When that worker is carrying
              more than its share, the ring walks forward to the next one.
              Affinity while there is room, spillover when there is not.
            </p>
          </div>

          <figure className="lp-ring" aria-label="The worker fleet as a hash ring">
            <Ring workers={workers.map((w) => w.id)} active={ranOn} />
            <figcaption>
              {workers.length > 0
                ? `${workers.length} workers online${ranOn ? "; the highlighted one ran your call" : ""}`
                : "Waiting for the fleet to report in"}
            </figcaption>
          </figure>
        </section>

        <section className="lp-facts">
          <dl>
            <div>
              <dt>Isolation</dt>
              <dd>
                Each function runs in its own container with 128MB, half a core,
                no network, and a 30 second kill timer enforced inside the
                container.
              </dd>
            </div>
            <div>
              <dt>When the fleet is full</dt>
              <dd>
                Requests are refused with a 503, not queued. Queueing does not
                create capacity; it just hides the wait somewhere less visible.
              </dd>
            </div>
            <div>
              <dt>When a worker dies</dt>
              <dd>
                Workers hold a Redis key with a 15 second expiry. Stop
                heartbeating and you leave the ring. In-flight calls fail over to
                another machine.
              </dd>
            </div>
            <div>
              <dt>Where it runs</dt>
              <dd>
                Docker Compose locally, or Terraform to AWS: the API on Fargate,
                the workers on EC2, because a machine that runs containers needs
                a Docker daemon.
              </dd>
            </div>
          </dl>
        </section>

        <section className="lp-go">
          <h2>Have a look around</h2>
          <div className="lp-go-links">
            <Link className="lp-go-primary" to="/cluster">
              Watch the fleet
            </Link>
            <Link className="lp-go-secondary" to="/functions">
              Read the deployed functions
            </Link>
          </div>
          <p className="lp-fineprint">
            This deployment is read-only, so the editor is disabled. Everything
            else works, including invoking the functions.
          </p>
        </section>
      </main>

      <footer className="lp-foot">
        <span>Built by Islam Assanov</span>
        <a
          href="https://github.com/islamborghini/clowdy"
          target="_blank"
          rel="noreferrer"
        >
          github.com/islamborghini/clowdy
        </a>
      </footer>
    </div>
  )
}

/**
 * The fleet drawn as the ring the scheduler actually hashes onto.
 *
 * One arc per worker, sized evenly, with the worker that served the live call
 * drawn in the warm colour. It is a diagram of the mechanism, not decoration,
 * so it only renders once the fleet has reported in.
 */
function Ring({ workers, active }: { workers: string[]; active: string | null }) {
  const size = 260
  const center = size / 2
  const radius = 96
  const gap = 0.09 // radians of empty space between arcs

  if (workers.length === 0) {
    return (
      <svg viewBox={`0 0 ${size} ${size}`} className="lp-ring-svg" aria-hidden="true">
        <circle cx={center} cy={center} r={radius} className="lp-ring-empty" />
      </svg>
    )
  }

  const step = (Math.PI * 2) / workers.length

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="lp-ring-svg" aria-hidden="true">
      <circle cx={center} cy={center} r={radius} className="lp-ring-empty" />
      {workers.map((id, i) => {
        const start = i * step - Math.PI / 2 + gap / 2
        const end = start + step - gap
        const x1 = center + radius * Math.cos(start)
        const y1 = center + radius * Math.sin(start)
        const x2 = center + radius * Math.cos(end)
        const y2 = center + radius * Math.sin(end)
        const largeArc = step - gap > Math.PI ? 1 : 0
        const mid = (start + end) / 2
        return (
          <g key={id}>
            <path
              d={`M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`}
              className={id === active ? "lp-arc lp-arc--active" : "lp-arc"}
            />
            <text
              x={center + (radius + 20) * Math.cos(mid)}
              y={center + (radius + 20) * Math.sin(mid)}
              className={id === active ? "lp-arc-label lp-arc-label--active" : "lp-arc-label"}
            >
              {id.slice(0, 4)}
            </text>
          </g>
        )
      })}
      <text x={center} y={center - 4} className="lp-ring-center">
        {workers.length}
      </text>
      <text x={center} y={center + 14} className="lp-ring-center-label">
        workers
      </text>
    </svg>
  )
}

const CSS = `
.lp {
  /* Cobalt is a cold start, amber is a warm hit. The palette carries the
     idea the whole architecture is built around, so it is never used
     decoratively anywhere else on the page. */
  --paper: #f2f4f6;
  --ink: #101720;
  --ink-soft: #4a5461;
  --rule: #d3dae1;
  --cold: #2f5fbf;
  --warm: #c2521a;

  background: var(--paper);
  color: var(--ink);
  font-family: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  line-height: 1.55;
}
.lp code { font-family: "IBM Plex Mono", ui-monospace, monospace; }
.lp a { color: inherit; }
.lp a:focus-visible,
.lp button:focus-visible {
  outline: 2px solid var(--cold);
  outline-offset: 3px;
}

.lp-bar {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.5rem clamp(1.25rem, 5vw, 4.5rem);
  border-bottom: 1px solid var(--rule);
  flex-wrap: wrap;
}
.lp-mark {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-weight: 600;
  font-size: 1.05rem;
  letter-spacing: -0.02em;
}
.lp-nav { display: flex; gap: 1.5rem; font-size: 0.9rem; }
.lp-nav a { text-decoration: none; border-bottom: 1px solid var(--rule); padding-bottom: 2px; }
.lp-nav a:hover { border-bottom-color: var(--ink); }

.lp main { flex: 1; }

.lp-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: clamp(2rem, 5vw, 4.5rem);
  align-items: start;
  padding: clamp(3rem, 8vw, 6rem) clamp(1.25rem, 5vw, 4.5rem);
  border-bottom: 1px solid var(--rule);
}
.lp-hero h1 {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: clamp(2.1rem, 5.2vw, 3.4rem);
  line-height: 1.08;
  letter-spacing: -0.035em;
  font-weight: 500;
  margin: 0 0 1.5rem;
  max-width: 16ch;
}
.lp-lede {
  font-size: 1.05rem;
  color: var(--ink-soft);
  max-width: 60ch;
  margin: 0 0 1rem;
}

.lp-measure {
  border: 1px solid var(--rule);
  background: #fff;
  padding: clamp(1.25rem, 3vw, 2rem);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
.lp-measure-pending { color: var(--ink-soft); font-size: 0.95rem; margin: 0; }
.lp-reading { display: grid; gap: 0.15rem; }
.lp-reading-label {
  font-size: 0.85rem;
  color: var(--ink-soft);
}
.lp-reading-value {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: clamp(2.4rem, 6vw, 3.5rem);
  line-height: 1;
  letter-spacing: -0.04em;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.lp-reading--cold .lp-reading-value { color: var(--cold); }
.lp-reading--warm .lp-reading-value { color: var(--warm); }
.lp-unit { font-size: 0.36em; margin-left: 0.25rem; letter-spacing: 0; }
.lp-reading-note { font-size: 0.88rem; color: var(--ink-soft); max-width: 34ch; }
.lp-fineprint { font-size: 0.85rem; color: var(--ink-soft); margin: 0; }

.lp-fleet {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: clamp(2rem, 5vw, 4.5rem);
  align-items: center;
  padding: clamp(3rem, 7vw, 5rem) clamp(1.25rem, 5vw, 4.5rem);
  border-bottom: 1px solid var(--rule);
}
.lp-fleet h2,
.lp-go h2 {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: clamp(1.4rem, 3vw, 1.9rem);
  letter-spacing: -0.03em;
  font-weight: 500;
  margin: 0 0 1rem;
}
.lp-fleet p { color: var(--ink-soft); max-width: 58ch; margin: 0 0 0.9rem; }
.lp-ring { margin: 0; display: grid; justify-items: center; gap: 0.75rem; }
.lp-ring-svg { width: min(260px, 80vw); height: auto; }
.lp-ring figcaption { font-size: 0.85rem; color: var(--ink-soft); text-align: center; }
.lp-ring-empty { fill: none; stroke: var(--rule); stroke-width: 1; }
.lp-arc { fill: none; stroke: var(--cold); stroke-width: 8; stroke-linecap: round; opacity: 0.32; }
.lp-arc--active { stroke: var(--warm); opacity: 1; }
.lp-arc-label {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 10px;
  fill: var(--ink-soft);
  text-anchor: middle;
  dominant-baseline: middle;
}
.lp-arc-label--active { fill: var(--warm); font-weight: 600; }
.lp-ring-center {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 26px; font-weight: 500; fill: var(--ink);
  text-anchor: middle;
}
.lp-ring-center-label {
  font-size: 10px; fill: var(--ink-soft); text-anchor: middle;
}

.lp-facts {
  padding: clamp(3rem, 7vw, 5rem) clamp(1.25rem, 5vw, 4.5rem);
  border-bottom: 1px solid var(--rule);
}
.lp-facts dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 2rem clamp(1.5rem, 4vw, 3rem);
  margin: 0;
}
.lp-facts dt {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.9rem;
  font-weight: 500;
  padding-bottom: 0.6rem;
  margin-bottom: 0.6rem;
  border-bottom: 1px solid var(--rule);
}
.lp-facts dd { margin: 0; color: var(--ink-soft); font-size: 0.95rem; max-width: 44ch; }

.lp-go { padding: clamp(3rem, 7vw, 5rem) clamp(1.25rem, 5vw, 4.5rem); }
.lp-go-links { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1rem; }
.lp a.lp-go-primary,
.lp a.lp-go-secondary {
  text-decoration: none;
  padding: 0.7rem 1.2rem;
  font-size: 0.95rem;
  border: 1px solid var(--ink);
}
.lp a.lp-go-primary { background: var(--ink); color: var(--paper); }
.lp a.lp-go-primary:hover { background: #000; }
.lp a.lp-go-secondary { border-color: var(--rule); }
.lp a.lp-go-secondary:hover { border-color: var(--ink); }

.lp-foot {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 1.5rem clamp(1.25rem, 5vw, 4.5rem);
  border-top: 1px solid var(--rule);
  font-size: 0.85rem;
  color: var(--ink-soft);
}

@media (max-width: 860px) {
  .lp-hero, .lp-fleet { grid-template-columns: 1fr; }
}
`
