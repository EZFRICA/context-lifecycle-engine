/* CLE dashboard — Alpine component. Reads snapshots + follows the oplog SSE.
   The ONLY writes are Approve / Decline (and the demo runner), all via the API
   which shells to the CLI. Metrics shown here are the HUMAN's window — never
   fed back to an agent (the Goodhart boundary lives in the copy too). */

const OP_ACCENT = {
  build: "teal", run: "teal", revalidate: "teal",
  closure_distribution: "blue",
  switch: "amber",
  topology_write: "violet",
  revalidation_failed: "coral", integrity_violation: "coral",
  candidate_declined: "coral",
  detector_observing: "faint", demo_step: "violet", demo_error: "coral",
};
const ACCENT_HEX = { teal: "#3dbf9b", blue: "#5aa9e6", amber: "#e8a33d",
  coral: "#e8705a", violet: "#9b8cf2", faint: "#6b7784", ink: "#dce3e8" };

// The op vocabulary we route on the SSE stream (event name = op).
const KNOWN_OPS = [
  "build", "run", "switch", "tag", "closure_distribution", "topology_write",
  "revalidate", "revalidation_failed", "integrity_violation", "detector_observing",
  "candidate_declined", "demo_step", "demo_error",
];
const LADDER = ["pinned", "ephemeral", "trial", "candidate", "archived"];

function short(h) { return h ? h.slice(0, 8) + "…" : "—"; }
function fmtTs(ts) { try { return new Date(ts).toLocaleTimeString(); } catch { return ""; } }
function pct(x) { return (x * 100).toFixed(1) + "%"; }

function cleDashboard() {
  return {
    connected: false, replayDone: false,
    pulse: [], candidates: [], images: [], ps: [],
    pulseView: 'live', decisions: [],
    topology: { version: 0, nodes: [], agents: {} }, versions: [],
    switches: [], shadowPairs: [], lastHumanTag: {},
    drift: null,
    diffA: null, diffB: null, diff: null,
    demo: { running: false, step: 0, total: 0, title: "", pace: 3000 },
    flash: { births: false, lives: false, topology: false },
    modal: { open: false, loading: false, agent: null, state: null, data: null },

    async init() {
      await this.refresh();
      this.connect();
      // Forward-compatibility + self-heal: periodic snapshot refresh keeps the
      // zones correct even if a novel op appears that PULSE doesn't route.
      setInterval(() => this.refresh(), 5000);
    },

    async loadDecisions() {
      // Sentences come rendered from the server (cle.oplog.render_decision).
      this.decisions = await fetch("/state/decisions").then(r => r.json());
    },

    async refresh() {
      try {
        const [c, i, p, t, v] = await Promise.all([
          fetch("/state/candidates").then(r => r.json()),
          fetch("/state/images").then(r => r.json()),
          fetch("/state/ps").then(r => r.json()),
          fetch("/state/topology").then(r => r.json()),
          fetch("/state/topology/versions").then(r => r.json()),
        ]);
        this.candidates = c; this.images = i; this.ps = p; this.topology = t; this.versions = v;
        if (this.diffA === null && v.length >= 2) { this.diffA = v[0]; this.diffB = v[v.length - 1]; }
      } catch (e) { /* transient during a CLI write; next tick recovers */ }
    },

    connect() {
      const es = new EventSource("/events");
      es.onopen = () => { this.connected = true; };
      es.onerror = () => { this.connected = false; };
      es.addEventListener("replay_complete", () => { this.replayDone = true; });
      KNOWN_OPS.forEach(op => es.addEventListener(op, e => this.onEvent(op, JSON.parse(e.data))));
    },

    onEvent(op, data) {
      if (op === "demo_step") return this.onDemoStep(data);
      this.pushPulse(op, data);
      if (op === "switch") this.onSwitch(data);
      if (op === "tag") this.onTag(data);
      if (op === "revalidation_failed") this.onDrift(data);
      // Replayed history populates PULSE + panels but must not flash/refresh
      // the whole board; only live events drive zone motion.
      if (!this.replayDone) return;
      // Any state-changing op refreshes the affected snapshots (debounced by the browser).
      if (["build", "run", "switch", "tag", "topology_write", "revalidation_failed",
           "candidate_declined", "revalidate"].includes(op)) {
        this.refresh();
        if (op === "build" || op === "closure_distribution") this.flashZone("births");
        else if (op === "topology_write") this.flashZone("topology");
        else this.flashZone("lives");
      }
    },

    pushPulse(op, data) {
      const accent = op === "tag" && data.actor === "engine:shadow" ? "violet"
        : (OP_ACCENT[op] || "faint");
      const line = {
        id: Math.random(), op, accent, ts: fmtTs(data.ts),
        band: op === "integrity_violation",
        msg: this.summarize(op, data),
      };
      this.pulse.unshift(line);
      if (this.pulse.length > 80) this.pulse.pop();
    },

    summarize(op, data) {
      const img = data.image ? short(data.image) : "";
      if (op === "demo_step")  return data.title ?? "";
      if (op === "demo_error") return data.title ?? "script error";
      if (op === "build") return `${img} pre_evidence capture=${pct(data.pre_evidence?.capture_rate ?? 0)} false=${pct(data.pre_evidence?.false_trigger_rate ?? 0)}`;
      if (op === "closure_distribution") return `closures success=${data.success ?? 0} reformulated=${data.reformulated ?? 0} abandoned=${data.abandoned ?? 0}`;
      if (op === "run") return `${data.workspace ?? ""} ${data.solicitations ?? "?"} solicitation(s) on ${img}`;
      if (op === "switch") return `${img} switch Δ ${data.diff_blocks} blk · ${data.diff_tokens} tok`;
      if (op === "tag") return data.actor === "engine:shadow"
        ? `engine:shadow ${img} would: ${data.would}`
        : `${data.from ?? "∅"} → ${data.to} on ${img}${data.reason ? " (" + data.reason + ")" : ""}`;
      if (op === "topology_write") return `topology v${data.version} ${data.to ?? ""} diff_size=${data.diff_size}`;
      if (op === "revalidate") return `${img} proof holds`;
      if (op === "revalidation_failed") return `${img} DRIFT ${data.persistence?.probe_deltas?.length ?? "?"} probes — proof expires`;
      if (op === "integrity_violation") return `INTEGRITY VIOLATION component ${data.component ?? "?"}`;
      if (op === "candidate_declined") return `declined ${data.agent} (was ${data.from})`;
      if (op === "detector_observing") return `detector observing (${data.episodes ?? "?"} episodes)`;
      return JSON.stringify(data).slice(0, 120);
    },


    onSwitch(data) {
      this.switches.unshift({ id: Math.random(), image: short(data.image),
        from: short(data.from), blocks: data.diff_blocks, tokens: data.diff_tokens, ts: fmtTs(data.ts) });
      if (this.switches.length > 6) this.switches.pop();
    },

    onTag(data) {
      if (data.actor === "engine:shadow") {
        const human = this.lastHumanTag[data.image];
        const would = data.would;
        const agree = human && (human === would);
        this.shadowPairs.unshift({ id: Math.random(), image: short(data.image),
          human: human || "—", would, agree: !!agree });
        if (this.shadowPairs.length > 8) this.shadowPairs.pop();
      } else if (data.to) {
        this.lastHumanTag[data.image] = data.to;
      }
    },

    onDrift(data) {
      this.drift = { image: short(data.image), pulse: this.replayDone,
        deltas: data.persistence?.probe_deltas?.length ?? 0,
        at: short(data.persistence?.fingerprint_at_build),
        now: short(data.persistence?.fingerprint_now) };
      setTimeout(() => { if (this.drift) this.drift.pulse = false; }, 1400);
    },

    onDemoStep(data) {
      this.demo.running = data.state === "start" || (this.demo.running && data.state !== "done" && data.state !== "aborted");
      this.demo.step = data.step; this.demo.total = data.total; this.demo.title = data.title;
      if (data.state === "done" || data.state === "aborted") { this.demo.running = false; this.demo.title = data.title; }
      if (data.zone && data.zone !== "pulse") this.flashZone(data.zone);
      this.pushPulse("demo_step", { ...data, ts: new Date().toISOString() });
    },

    flashZone(zone) {
      if (!(zone in this.flash)) return;
      this.flash[zone] = false;
      requestAnimationFrame(() => { this.flash[zone] = true;
        setTimeout(() => { this.flash[zone] = false; }, 650); });
    },

    // --- the one write path ---
    async approve(agent) {
      await fetch("/actions/approve", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent }) });
      this.refresh();
    },
    async decline(agent) {
      await fetch("/actions/decline", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent }) });
      this.refresh();
    },

    async startDemo() {
      const r = await fetch("/demo/start", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pace_ms: Number(this.demo.pace) }) });
      if (r.ok) this.demo.running = true;
    },
    async abortDemo() { await fetch("/demo/abort", { method: "POST" }); },

    // Shared POST helper: fires the request, reads the JSON result, then pushes
    // the outcome to the pulse so the user always sees stdout/stderr/exit code.
    async _postAction(url, pulseTitle, step) {
      const ts = new Date().toISOString();
      this.pushPulse("demo_step", { title: pulseTitle, step, total: 3, ts });
      this.demo.running = true;
      let result;
      try {
        const r = await fetch(url, { method: "POST" });
        result = await r.json();
      } catch (err) {
        this.pushPulse("demo_error", { title: `Network error: ${err.message}`, ts: new Date().toISOString() });
        this.demo.running = false;
        this.refresh();
        return;
      }
      const ok = result.code === 0;
      const op = ok ? "demo_step" : "demo_error";
      // Show last 8 non-empty lines of stdout (or stderr on failure).
      const raw = ok ? (result.stdout || "") : (result.stderr || result.stdout || "");
      const tail = raw.split("\n").map(l => l.trim()).filter(Boolean).slice(-8).join(" · ");
      const label = ok
        ? `✓ ${pulseTitle} — exit 0${tail ? " | " + tail : ""}`
        : `✗ ${pulseTitle} — exit ${result.code}${tail ? " | " + tail : ""}`;
      this.pushPulse(op, { title: label, step, total: 3, ts: new Date().toISOString() });
      this.demo.running = false;
      this.refresh();
    },

    async initSystem() {
      await this._postAction("/actions/init", "Initializing fixtures and candidate agent", 1);
    },

    async runSolicitations() {
      await this._postAction("/actions/run_workspaces", "Running full loop (full_loop.sh)", 2);
    },

    async reinitSystem() {
      // `cle clean` is rmtree on a gitignored directory: git cannot restore it,
      // and the dashboard's state dir is whatever the operator launched it
      // against, which may well be the live one. The CLI confirms, but this
      // action reaches it through a subprocess with no tty, so the confirmation
      // belongs here.
      // The path is deliberately not named here: the frontend does not know it,
      // and adding an endpoint to publish it would be a feature, not a cleanup.
      // The CLI prints the resolved path in the action output.
      if (!window.confirm("Delete all persistent CLE state?\n\nThis is the only copy: the state directory is gitignored, so git cannot restore it.")) {
        return;
      }
      await this._postAction("/actions/clean", "Cleaning local CLE state", 3);
    },

    // --- agent detail modal ---
    openAgent(agent, state, imageHash) {
      this.modal = { open: true, loading: true, agent, state, data: null };
      fetch(`/state/image?hash=${imageHash}`)
        .then(r => r.json())
        .then(d => { this.modal.data = d; this.modal.loading = false; })
        .catch(() => { this.modal.loading = false; });
    },
    closeModal() { this.modal.open = false; },
    fmtPeriod(seconds) {
      if (!seconds) return "—";
      const d = seconds / 86400;
      return d >= 1 ? `${d.toFixed(1)} d` : `${(seconds / 3600).toFixed(1)} h`;
    },

    async loadDiff() {
      if (this.diffA == null || this.diffB == null) return;
      this.diff = await fetch(`/state/topology/diff?a=${this.diffA}&b=${this.diffB}`).then(r => r.ok ? r.json() : null);
    },

    // --- view helpers ---
    accentHex(a) { return ACCENT_HEX[a] || ACCENT_HEX.ink; },
    stateVar(s) { return `var(--s-${s})`; },
    agentsInState(state) { return (this.topology.nodes || []).filter(n => n.state === state); },
    fmtPct: pct, short, fmtTs,
  };
}
window.cleDashboard = cleDashboard;
