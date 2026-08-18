import { useState, useEffect, useRef } from "react";

// EvalGauge dashboard — a monitoring console for a jailbreak-detection pipeline.
// Design intent: instrument panel, not marketing page. Monospace data, restrained
// signal colors, one signature interaction — the intervention toggle that moves
// catch-rate and false-positive burden together, which is the project's whole thesis.

const FAMILIES = [
  { name: "role-play / persona", base: 0.91, mitigated: 0.97 },
  { name: "prefix-injection", base: 0.88, mitigated: 0.95 },
  { name: "encoding / obfuscation", base: 0.62, mitigated: 0.79 },
  { name: "many-shot", base: 0.71, mitigated: 0.9 },
  { name: "gradual escalation", base: 0.54, mitigated: 0.68 },
  { name: "novel (synthetic)", base: 0.43, mitigated: 0.55 },
];

const C = {
  bg: "#0d1117",
  panel: "#141b24",
  line: "#232d3a",
  text: "#c9d4e0",
  dim: "#6b7787",
  caught: "#3fb6a8",   // signal: adversarial caught
  fp: "#e0733f",       // cost: benign blocked — the thing you must not ignore
  miss: "#4a5568",
  mono: "ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, monospace",
};

function Stat({ label, value, unit, color, sub }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: 1, color: C.dim, textTransform: "uppercase" }}>{label}</span>
      <span style={{ fontFamily: C.mono, fontSize: 34, fontWeight: 600, color, lineHeight: 1 }}>
        {value}<span style={{ fontSize: 16, color: C.dim, marginLeft: 2 }}>{unit}</span>
      </span>
      {sub && <span style={{ fontFamily: C.mono, fontSize: 11, color: C.dim }}>{sub}</span>}
    </div>
  );
}

export default function Dashboard() {
  const [mitigated, setMitigated] = useState(false);
  const [feed, setFeed] = useState([]);
  const idRef = useRef(4021);

  useEffect(() => {
    const id = setInterval(() => {
      const fam = FAMILIES[Math.floor(Math.random() * FAMILIES.length)];
      const benign = Math.random() < 0.55;
      const rate = mitigated ? fam.mitigated : fam.base;
      const caught = benign ? Math.random() < (mitigated ? 0.03 : 0.06) : Math.random() < rate;
      idRef.current += 1;
      const row = {
        id: idRef.current,
        kind: benign ? "benign" : fam.name,
        benign,
        flagged: caught,
        tier: Math.random() < 0.7 ? "fast" : "judge",
        ms: benign ? 12 + Math.floor(Math.random() * 8) : (Math.random() < 0.7 ? 14 + Math.floor(Math.random() * 10) : 340 + Math.floor(Math.random() * 120)),
      };
      setFeed((f) => [row, ...f].slice(0, 9));
    }, 900);
    return () => clearInterval(id);
  }, [mitigated]);

  const catchRate = Math.round(
    (FAMILIES.reduce((s, f) => s + (mitigated ? f.mitigated : f.base), 0) / FAMILIES.length) * 100
  );
  const fpBurden = mitigated ? 2.9 : 5.7;

  return (
    <div style={{ background: C.bg, color: C.text, fontFamily: "system-ui, sans-serif", padding: 24, minHeight: 640 }}>
      {/* header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", borderBottom: `1px solid ${C.line}`, paddingBottom: 14, marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <span style={{ fontFamily: C.mono, fontSize: 20, fontWeight: 700, letterSpacing: 1 }}>EVALGAUGE</span>
          <span style={{ fontFamily: C.mono, fontSize: 11, color: C.dim }}>jailbreak detection · live</span>
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", fontFamily: C.mono, fontSize: 12 }}>
          <span style={{ color: mitigated ? C.caught : C.dim }}>mitigation {mitigated ? "ON" : "OFF"}</span>
          <span
            onClick={() => setMitigated((m) => !m)}
            style={{ width: 42, height: 22, borderRadius: 11, background: mitigated ? C.caught : C.line, position: "relative", transition: "background .25s" }}
          >
            <span style={{ position: "absolute", top: 2, left: mitigated ? 22 : 2, width: 18, height: 18, borderRadius: 9, background: "#fff", transition: "left .25s" }} />
          </span>
        </label>
      </div>

      {/* top stats — catch rate and FP burden side by side, always together */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 20 }}>
        <div style={{ background: C.panel, border: `1px solid ${C.line}`, borderRadius: 8, padding: 18 }}>
          <Stat label="catch rate" value={catchRate} unit="%" color={C.caught} sub="mean across families" />
        </div>
        <div style={{ background: C.panel, border: `1px solid ${C.line}`, borderRadius: 8, padding: 18 }}>
          <Stat label="false-positive burden" value={fpBurden} unit="%" color={C.fp} sub="benign traffic blocked" />
        </div>
        <div style={{ background: C.panel, border: `1px solid ${C.line}`, borderRadius: 8, padding: 18 }}>
          <Stat label="judge escalation" value={mitigated ? 31 : 28} unit="%" color={C.text} sub="tier-2 of all events" />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 16 }}>
        {/* per-family — the anti-aggregate view */}
        <div style={{ background: C.panel, border: `1px solid ${C.line}`, borderRadius: 8, padding: 18 }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: 1, color: C.dim, textTransform: "uppercase", marginBottom: 14 }}>
            catch rate by family
          </div>
          {FAMILIES.map((f) => {
            const r = mitigated ? f.mitigated : f.base;
            return (
              <div key={f.name} style={{ marginBottom: 11 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontFamily: C.mono, fontSize: 12, marginBottom: 3 }}>
                  <span style={{ color: r < 0.6 ? C.fp : C.text }}>{f.name}</span>
                  <span style={{ color: C.dim }}>{Math.round(r * 100)}%</span>
                </div>
                <div style={{ height: 5, background: C.line, borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ width: `${r * 100}%`, height: "100%", background: r < 0.6 ? C.fp : C.caught, transition: "width .35s" }} />
                </div>
              </div>
            );
          })}
          <div style={{ fontFamily: C.mono, fontSize: 10, color: C.dim, marginTop: 12, lineHeight: 1.5 }}>
            the weak families are the point. an aggregate score hides the two in orange.
          </div>
        </div>

        {/* live feed */}
        <div style={{ background: C.panel, border: `1px solid ${C.line}`, borderRadius: 8, padding: 18 }}>
          <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: 1, color: C.dim, textTransform: "uppercase", marginBottom: 14 }}>
            event stream
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {feed.map((r) => (
              <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 10, fontFamily: C.mono, fontSize: 11.5 }}>
                <span style={{ color: C.dim, width: 44 }}>#{r.id}</span>
                <span style={{ width: 8, height: 8, borderRadius: 4, background: r.benign ? (r.flagged ? C.fp : C.miss) : (r.flagged ? C.caught : C.fp), flexShrink: 0 }} />
                <span style={{ flex: 1, color: r.benign ? C.dim : C.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {r.benign ? "benign" : r.kind}
                </span>
                <span style={{ color: C.dim, width: 40 }}>{r.tier}</span>
                <span style={{ color: r.ms > 300 ? C.fp : C.dim, width: 52, textAlign: "right" }}>{r.ms}ms</span>
              </div>
            ))}
          </div>
          <div style={{ fontFamily: C.mono, fontSize: 10, color: C.dim, marginTop: 14, lineHeight: 1.5 }}>
            orange dot on a benign row = false positive. orange latency = judge tier.
          </div>
        </div>
      </div>

      <div style={{ fontFamily: C.mono, fontSize: 10, color: C.dim, marginTop: 18, textAlign: "center" }}>
        controlled measurement over labeled data · numbers illustrative in this mock · flip the toggle
      </div>
    </div>
  );
}
