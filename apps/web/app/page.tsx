"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
// ── Domain types ──────────────────────────────────────────────────────────────

type CabinetScope = {
  id: string;
  name: string;
  format: "season" | "ladder" | "tournament";
  current_week: number;
};

type StandingsRow = {
  cabinet_id: string;
  cabinet_name: string;
  total_points: number;
  rank: number;
};

type StandingsResponse = {
  scope_id: string;
  week: number;
  items: StandingsRow[];
};

type Cabinet = {
  id: string;
  scope_id: string;
  manager_user_id: string;
  name: string;
  created_at: string;
};

type UserProfile = {
  id: string;
  display_name: string;
  email?: string | null;
  roles: string[];
  issuer?: string | null;
};

/** A real politician who can fill a portfolio seat. */
type MP = {
  id: string;
  name: string;        // display name (= full_name)
  full_name: string;
  current_role: string;
  role_tier: number;
  jurisdiction: string;
  asset_type: string;
  party: string;
  status: "active" | "pending" | "ineligible" | "retired";
  aliases: string[];
  source: string;
  last_verified_at?: string | null;
};

/** One MP assigned to one portfolio seat in a cabinet. */
type PortfolioSeat = {
  roster_slot_id: number;
  slot: string;
  slot_label: string;
  asset_id: string;
  asset_name: string;
  jurisdiction: string;
  asset_type: string;
  party: string;
  lineup_status: "active" | "bench";
};

type PolicyObjective = {
  id: string;
  name: string;
  description: string;
  event_types: string[];
  bonus: number;
};

type LedgerEntry = {
  id: string;
  week: number;
  event: string;
  points: number;
  attribution_id?: string | null;
  politician_id?: string | null;
  created_at: string;
};

type ParliamentaryEvent = {
  id: string;
  title: string;
  source_name: string;
  jurisdiction: string;
  event_type: string;
  occurred_at: string;
  url?: string;
};

type BenchSignal = {
  politician_id: string;
  politician_name: string;
  article_count: number;
  top_significance: number;
  top_story_title: string | null;
  top_story_id: string | null;
};

type DailyDigestTopStory = {
  id: string;
  canonical_title: string;
  significance: number;
  event_type: string;
  jurisdiction: string;
  article_count: number;
};

type DailyDigestMPActivity = {
  politician_id: string;
  politician_name: string;
  article_count: number;
};

type DailyDigestBenchAlert = {
  politician_id: string;
  politician_name: string;
  article_count: number;
  in_news: boolean;
};

type DailyDigest = {
  top_stories: DailyDigestTopStory[];
  active_mps_in_news: DailyDigestMPActivity[];
  bench_alerts: DailyDigestBenchAlert[];
  total_articles_today: number;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const ONBOARDING_KEY = "fc_onboarding_v4";

const PARTY_COLOURS: Record<string, string> = {
  Liberal:      "#c0392b",
  Conservative: "#2980b9",
  NDP:          "#e67e22",
  Bloc:         "#8e44ad",
  CAQ:          "#16a085",
  PQ:           "#2471a3",
  UCP:          "#cb4335",
  Green:        "#27ae60",
  independent:  "#7f8c8d",
};

const STEPS = [
  "How the game works",
  "Choose a cabinet scope",
  "Assemble your cabinet",
  "Set policy objectives",
  "Set your mandate",
];

// ── Shared helpers ────────────────────────────────────────────────────────────

function PartyBadge({ party }: { party: string }) {
  const bg = PARTY_COLOURS[party] ?? PARTY_COLOURS.independent;
  return <span className="party-badge" style={{ background: bg }}>{party}</span>;
}

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = "Request failed";
    try { const j = await res.json() as { detail?: string }; detail = j.detail ?? detail; } catch { /**/ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ── Main component ────────────────────────────────────────────────────────────

export default function HomePage() {
  const [profile, setProfile]                           = useState<UserProfile | null>(null);
  const [scopes, setScopes]                             = useState<CabinetScope[]>([]);
  const [selectedScopeId, setSelectedScopeId]           = useState<string>("");
  const [standings, setStandings]                       = useState<StandingsResponse | null>(null);
  const [events, setEvents]                             = useState<ParliamentaryEvent[]>([]);
  const [cabinets, setCabinets]                         = useState<Cabinet[]>([]);
  const [selectedCabinetId, setSelectedCabinetId]       = useState<string>("");
  const [portfolio, setPortfolio]                       = useState<PortfolioSeat[]>([]);
  const [allMPs, setAllMPs]                             = useState<MP[]>([]);
  const [editingSeatSlot, setEditingSeatSlot]           = useState<string | null>(null);
  const [policyObjectives, setPolicyObjectives]         = useState<PolicyObjective[]>([]);
  const [selectedObjectiveIds, setSelectedObjectiveIds] = useState<string[]>([]);
  const [savingObjectives, setSavingObjectives]         = useState(false);
  const [ledger, setLedger]                             = useState<LedgerEntry[]>([]);
  const [savingMandate, setSavingMandate]               = useState(false);
  const [hydrated, setHydrated]                         = useState(false);
  const [onboardingDone, setOnboardingDone]             = useState(false);
  const [step, setStep]                                 = useState(0);
  const [creatingScope, setCreatingScope]               = useState(false);
  const [creatingCabinet, setCreatingCabinet]           = useState(false);
  const [newScopeName, setNewScopeName]                 = useState("");
  const [newCabinetName, setNewCabinetName]             = useState("");
  const [loading, setLoading]                           = useState(true);
  const [running, setRunning]                           = useState(false);
  const [error, setError]                               = useState("");
  const [notice, setNotice]                             = useState("");
  const [dailyDigest, setDailyDigest]                   = useState<DailyDigest | null>(null);
  const [benchSignals, setBenchSignals]                 = useState<BenchSignal[]>([]);

  const governingSeats  = portfolio.filter((s) => s.lineup_status === "active");
  const monitoringSeats = portfolio.filter((s) => s.lineup_status === "bench");
  const selectedScope   = useMemo(() => scopes.find((s) => s.id === selectedScopeId), [scopes, selectedScopeId]);
  const myCabinets      = useMemo(
    () => profile ? cabinets.filter((c) => c.manager_user_id === profile.id) : cabinets,
    [cabinets, profile],
  );

  // ── loaders ───────────────────────────────────────────────────────────────

  async function loadProfile() {
    try { const b = await readJson<UserProfile>(`${apiBase}/api/v1/auth/me`); setProfile(b); return b; }
    catch { return null; }
  }

  async function loadScopes() {
    setLoading(true);
    try {
      const b = await readJson<{ items: CabinetScope[] }>(`${apiBase}/api/v1/cabinet-scopes`);
      setScopes(b.items);
      setSelectedScopeId((cur) => cur || b.items[0]?.id || "");
    } catch { setError("Could not load cabinet scopes."); }
    finally { setLoading(false); }
  }

  async function loadStandings(scopeId: string) {
    if (!scopeId) { setStandings(null); return; }
    try { setStandings(await readJson<StandingsResponse>(`${apiBase}/api/v1/cabinet-scopes/${scopeId}/standings`)); }
    catch { /* non-fatal */ }
  }

  async function loadCabinets(scopeId: string, managerId?: string) {
    try {
      const b = await readJson<{ items: Cabinet[] }>(`${apiBase}/api/v1/cabinet-scopes/${scopeId}/cabinets`);
      setCabinets(b.items);
      const pref = managerId ? b.items.find((c) => c.manager_user_id === managerId) : undefined;
      setSelectedCabinetId((cur) => {
        if (cur && b.items.some((c) => c.id === cur)) return cur;
        return pref?.id ?? b.items[0]?.id ?? "";
      });
    } catch { /* non-fatal */ }
  }

  async function loadPortfolio(cabinetId: string) {
    if (!cabinetId) { setPortfolio([]); return; }
    try {
      const b = await readJson<{ cabinet_id: string; items: PortfolioSeat[] }>(
        `${apiBase}/api/v1/cabinets/${cabinetId}/portfolio`,
      );
      setPortfolio(b.items);
    } catch { setError("Could not load portfolio."); }
  }

  async function loadMPs() {
    try {
      const b = await readJson<{ items: MP[] }>(`${apiBase}/api/v1/politicians`);
      setAllMPs(b.items);
    } catch { /* non-fatal */ }
  }

  async function loadPolicyObjectives() {
    try {
      const b = await readJson<{ items: PolicyObjective[] }>(`${apiBase}/api/v1/policy-objectives`);
      setPolicyObjectives(b.items);
    } catch { /* non-fatal */ }
  }

  async function loadCabinetObjectives(cabinetId: string) {
    if (!cabinetId) return;
    try {
      const b = await readJson<{ cabinet_id: string; items: string[] }>(
        `${apiBase}/api/v1/cabinets/${cabinetId}/policy-objectives`,
      );
      setSelectedObjectiveIds(b.items);
    } catch { /* non-fatal */ }
  }

  async function loadLedger(cabinetId: string, scopeId: string) {
    if (!cabinetId || !scopeId) return;
    try {
      const b = await readJson<{ items: LedgerEntry[] }>(
        `${apiBase}/api/v1/cabinets/${cabinetId}/ledger?scope_id=${scopeId}`,
      );
      setLedger(b.items);
    } catch { setLedger([]); }
  }

  async function loadEvents() {
    try {
      const b = await readJson<{ items: ParliamentaryEvent[] }>(`${apiBase}/api/v1/events?limit=15`);
      setEvents(b.items);
    } catch { /**/ }
  }

  async function loadDailyDigest(cabinetId: string) {
    if (!cabinetId) return;
    try {
      const b = await readJson<DailyDigest>(`${apiBase}/api/v1/cabinets/${cabinetId}/daily-digest`);
      setDailyDigest(b);
    } catch { /* non-fatal */ }
  }

  async function loadBenchSignals(cabinetId: string) {
    if (!cabinetId) return;
    try {
      const b = await readJson<{ items: BenchSignal[] }>(`${apiBase}/api/v1/cabinets/${cabinetId}/bench-signals`);
      setBenchSignals(b.items);
    } catch { /* non-fatal */ }
  }

  // ── MP seat assignment ────────────────────────────────────────────────────

  async function assignMP(slotName: string, mpId: string) {
    if (!selectedCabinetId) return;
    setError("");
    try {
      await readJson<PortfolioSeat>(`${apiBase}/api/v1/cabinets/${selectedCabinetId}/portfolio/${slotName}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mp_id: mpId }),
      });
      setEditingSeatSlot(null);
      await loadPortfolio(selectedCabinetId);
      setNotice("MP assigned to seat.");
    } catch (e) { setError(String(e)); }
  }

  // ── policy objectives ─────────────────────────────────────────────────────

  function toggleObjective(id: string) {
    setSelectedObjectiveIds((cur) => {
      if (cur.includes(id)) return cur.filter((x) => x !== id);
      if (cur.length >= 2) { setError("Select at most 2 policy objectives."); return cur; }
      setError("");
      return [...cur, id];
    });
  }

  async function savePolicyObjectives(): Promise<boolean> {
    if (!selectedCabinetId) return false;
    setSavingObjectives(true); setError("");
    try {
      await readJson<unknown>(`${apiBase}/api/v1/cabinets/${selectedCabinetId}/policy-objectives`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective_ids: selectedObjectiveIds }),
      });
      setNotice("Policy objectives saved.");
      return true;
    } catch { setError("Could not save policy objectives."); return false; }
    finally { setSavingObjectives(false); }
  }

  // ── mandate helpers ───────────────────────────────────────────────────────

  function toggleSeat(id: number, governing: boolean) {
    setPortfolio((cur) =>
      cur.map((s) => s.roster_slot_id === id ? { ...s, lineup_status: governing ? "active" : "bench" } : s)
    );
  }

  function autoBalance() {
    const fed  = portfolio.filter((s) => s.jurisdiction.toLowerCase() === "federal");
    const prov = portfolio.filter((s) => s.jurisdiction.toLowerCase() !== "federal");
    const picks: number[] = [];
    if (fed[0])  picks.push(fed[0].roster_slot_id);
    if (prov[0]) picks.push(prov[0].roster_slot_id);
    for (const s of portfolio) {
      if (picks.length >= 4) break;
      if (!picks.includes(s.roster_slot_id)) picks.push(s.roster_slot_id);
    }
    setPortfolio((cur) => cur.map((s) => ({ ...s, lineup_status: picks.includes(s.roster_slot_id) ? "active" : "bench" })));
    setNotice("Auto-balanced: 4 governing seats with federal/provincial coverage.");
  }

  function validateMandate(): string | null {
    const active = portfolio.filter((s) => s.lineup_status === "active");
    if (active.length !== 4) return "Mandate must have exactly 4 governing seats.";
    if (!active.some((s) => s.jurisdiction.toLowerCase() === "federal")) return "At least 1 governing seat must be federal.";
    if (!active.some((s) => s.jurisdiction.toLowerCase() !== "federal")) return "At least 1 governing seat must be provincial.";
    return null;
  }

  async function saveMandate(): Promise<boolean> {
    if (!selectedCabinetId) return false;
    const err = validateMandate();
    if (err) { setError(err); return false; }
    setSavingMandate(true); setError("");
    try {
      await readJson<unknown>(`${apiBase}/api/v1/cabinets/${selectedCabinetId}/mandate`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slots: portfolio.map((s) => ({ roster_slot_id: s.roster_slot_id, lineup_status: s.lineup_status })),
        }),
      });
      await loadPortfolio(selectedCabinetId);
      setNotice("Mandate saved.");
      return true;
    } catch { setError("Could not save mandate."); return false; }
    finally { setSavingMandate(false); }
  }

  // ── scoring ───────────────────────────────────────────────────────────────

  async function runScoring() {
    if (!selectedScopeId) return;
    setRunning(true); setError("");
    try {
      await readJson<unknown>(`${apiBase}/api/v1/internal/scoring/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ league_id: selectedScopeId }),
      });
      await Promise.all([
        loadStandings(selectedScopeId),
        loadScopes(),
        loadEvents(),
        loadPortfolio(selectedCabinetId),
        loadLedger(selectedCabinetId, selectedScopeId),
      ]);
    } catch { setError("Scoring run failed."); }
    finally { setRunning(false); }
  }

  // ── scope / cabinet creation ──────────────────────────────────────────────

  async function createScope() {
    const name = newScopeName.trim();
    if (!name) { setError("Enter a scope name."); return; }
    setCreatingScope(true); setError("");
    try {
      const c = await readJson<CabinetScope>(`${apiBase}/api/v1/cabinet-scopes`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, format: "season" }),
      });
      setNewScopeName(""); await loadScopes(); setSelectedScopeId(c.id);
      setNotice(`Cabinet scope created: ${c.name}`);
    } catch { setError("Could not create scope."); }
    finally { setCreatingScope(false); }
  }

  async function createCabinet() {
    if (!selectedScopeId) { setError("Select a cabinet scope first."); return; }
    const name = newCabinetName.trim();
    if (!name) { setError("Enter a cabinet name."); return; }
    setCreatingCabinet(true); setError("");
    try {
      const c = await readJson<Cabinet>(`${apiBase}/api/v1/cabinet-scopes/${selectedScopeId}/cabinets`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      setNewCabinetName("");
      await loadCabinets(selectedScopeId, profile?.id);
      setSelectedCabinetId(c.id);
      await loadPortfolio(c.id);
      setNotice(`Cabinet created: ${c.name}`);
    } catch { setError("Could not create cabinet."); }
    finally { setCreatingCabinet(false); }
  }

  // ── onboarding ────────────────────────────────────────────────────────────

  function goToStep(n: number) { setError(""); setNotice(""); setStep(Math.max(0, Math.min(STEPS.length - 1, n))); }

  async function continueOnboarding() {
    if (step === 1 && !selectedScopeId) { setError("Select or create a cabinet scope first."); return; }
    if (step === 2 && !selectedCabinetId) { setError("Create or select a cabinet first."); return; }
    if (step === 3) {
      const ok = await savePolicyObjectives();
      if (!ok) return;
    }
    if (step === 4) {
      const ok = await saveMandate();
      if (!ok) return;
      setOnboardingDone(true);
      window.localStorage.setItem(ONBOARDING_KEY, "true");
      setNotice("Your cabinet is ready. Good luck!");
      return;
    }
    goToStep(step + 1);
  }

  function resetOnboarding() {
    window.localStorage.removeItem(ONBOARDING_KEY);
    setOnboardingDone(false); setStep(0);
    setNotice("Onboarding restarted."); setError("");
  }

  // ── effects ───────────────────────────────────────────────────────────────

  useEffect(() => {
    setOnboardingDone(window.localStorage.getItem(ONBOARDING_KEY) === "true");
    setHydrated(true);
    void (async () => {
      const me = await loadProfile();
      await Promise.all([loadScopes(), loadEvents(), loadMPs(), loadPolicyObjectives()]);
      if (selectedScopeId) await loadCabinets(selectedScopeId, me?.id);
    })();
  }, []);

  useEffect(() => {
    if (selectedScopeId) {
      void loadStandings(selectedScopeId);
      void loadCabinets(selectedScopeId, profile?.id);
    }
  }, [selectedScopeId, profile?.id]);

  useEffect(() => {
    if (selectedCabinetId) {
      void loadPortfolio(selectedCabinetId);
      void loadCabinetObjectives(selectedCabinetId);
      void loadDailyDigest(selectedCabinetId);
      void loadBenchSignals(selectedCabinetId);
      if (selectedScopeId) void loadLedger(selectedCabinetId, selectedScopeId);
    }
  }, [selectedCabinetId, selectedScopeId]);

  if (!hydrated) return <main><h1>FantasyCabinet</h1><p className="muted">Loading…</p></main>;

  // ── render ────────────────────────────────────────────────────────────────

  const isCommissioner = profile?.roles.includes("commissioner") || profile?.roles.includes("admin");

  return (
    <main>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "0.25rem" }}>
        <h1 style={{ margin: 0 }}>FantasyCabinet</h1>
        {isCommissioner && (
          <a href="/admin" style={{ fontSize: "0.875rem", opacity: 0.85 }}>⚙ Admin centre</a>
        )}
      </div>
      <p>Build a cabinet of Canadian MPs, set your governing mandate, and score from real parliamentary events.</p>

      {/* ── Replay onboarding ── */}
      {onboardingDone && (
        <section className="card">
          <div className="row">
            <h2 style={{ margin: 0 }}>Setup guide</h2>
            <button type="button" onClick={resetOnboarding}>Replay onboarding</button>
          </div>
          <p className="muted">Walk through cabinet setup from the beginning.</p>
        </section>
      )}

      {/* ── Onboarding wizard ── */}
      {!onboardingDone && (
        <section className="card onboarding">
          <h2>Welcome to FantasyCabinet</h2>
          {profile && <p className="muted">Signed in as <strong>{profile.display_name}</strong></p>}

          <ol className="onboarding-steps">
            {STEPS.map((s, i) => (
              <li key={s} className={i === step ? "active-step" : ""}>
                <button type="button" onClick={() => goToStep(i)}>{i + 1}. {s}</button>
              </li>
            ))}
          </ol>

          {/* Step 0 — How the game works */}
          {step === 0 && (
            <div className="onboarding-panel">
              <h3>How the game works</h3>
              <ul>
                <li><strong>MPs are the players.</strong> Real Canadian politicians — the PM, premiers, cabinet ministers, opposition leaders.</li>
                <li><strong>Your cabinet is your team.</strong> 6 portfolio seats. You choose which MP fills each one.</li>
                <li><strong>A cabinet scope is the competition.</strong> All managers inside a scope compete for weekly standings.</li>
                <li><strong>The mandate is your weekly strategy.</strong> Exactly 4 of your 6 seats are &ldquo;governing&rdquo; — those score. The other 2 are &ldquo;monitoring&rdquo; reserves.</li>
                <li><strong>Policy objectives add bonuses.</strong> Choose up to 2 objectives (economy, health, climate…) and earn bonus points when matching events occur.</li>
                <li><strong>Parliamentary events drive scoring.</strong> Bills, confidence votes, scandals, policy milestones — scored automatically from real news each cycle.</li>
                <li><strong>Party affinity and role type matter.</strong> An executive MP scores more on executive events. A party in the headlines gets a bonus.</li>
                <li><strong>Ethics violations hurt.</strong> Scandals and confidence defeats carry negative points.</li>
              </ul>
            </div>
          )}

          {/* Step 1 — Choose scope */}
          {step === 1 && (
            <div className="onboarding-panel">
              <h3>Choose a cabinet scope</h3>
              <p className="muted">A cabinet scope is a seasonal or rolling competition. Join an existing scope or create one.</p>
              <div className="row">
                <label htmlFor="ob-scope">Active scopes</label>
                <select id="ob-scope" value={selectedScopeId} onChange={(e) => setSelectedScopeId(e.target.value)} disabled={loading || !scopes.length}>
                  {scopes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div className="row onboarding-create-row">
                <input type="text" placeholder="Name a new cabinet scope" value={newScopeName} onChange={(e) => setNewScopeName(e.target.value)} />
                <button type="button" onClick={createScope} disabled={creatingScope}>{creatingScope ? "Creating…" : "Create scope"}</button>
              </div>
            </div>
          )}

          {/* Step 2 — Assemble cabinet */}
          {step === 2 && (
            <div className="onboarding-panel">
              <h3>Assemble your cabinet</h3>
              <p className="muted">Create a cabinet — MPs are auto-assigned to the 6 seats. Use <strong>Change MP</strong> on any row to swap in whichever MP you want.</p>
              <div className="row onboarding-create-row">
                <input type="text" placeholder="Name your cabinet" value={newCabinetName} onChange={(e) => setNewCabinetName(e.target.value)} />
                <button type="button" onClick={createCabinet} disabled={creatingCabinet || !selectedScopeId}>
                  {creatingCabinet ? "Creating…" : "Create cabinet"}
                </button>
              </div>
              {myCabinets.length > 0 && (
                <div className="row" style={{ marginTop: "0.6rem" }}>
                  <label htmlFor="ob-cabinet">Your cabinets</label>
                  <select id="ob-cabinet" value={selectedCabinetId} onChange={(e) => setSelectedCabinetId(e.target.value)}>
                    {myCabinets.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
              )}
              {portfolio.length > 0 && (
                <MPPicker
                  portfolio={portfolio}
                  allMPs={allMPs}
                  editingSeatSlot={editingSeatSlot}
                  setEditingSeatSlot={setEditingSeatSlot}
                  onAssign={assignMP}
                  benchSignals={benchSignals}
                />
              )}
              {portfolio.length === 0 && selectedCabinetId && <p className="muted">Loading portfolio…</p>}
            </div>
          )}

          {/* Step 3 — Policy objectives */}
          {step === 3 && (
            <div className="onboarding-panel">
              <h3>Set policy objectives</h3>
              <p className="muted">Choose up to 2 objectives. Matching parliamentary events earn you a bonus on top of standard scoring.</p>
              <p className="muted">Selected: <strong>{selectedObjectiveIds.length} / 2</strong></p>
              {policyObjectives.length === 0
                ? <p className="muted">Loading objectives…</p>
                : (
                  <div className="objective-grid">
                    {policyObjectives.map((obj) => {
                      const active = selectedObjectiveIds.includes(obj.id);
                      return (
                        <div
                          key={obj.id}
                          className={`objective-card${active ? " objective-active" : ""}`}
                          onClick={() => toggleObjective(obj.id)}
                          role="checkbox"
                          aria-checked={active}
                          tabIndex={0}
                          onKeyDown={(e) => e.key === " " && toggleObjective(obj.id)}
                        >
                          <div className="objective-name">{obj.name}</div>
                          <div className="muted objective-desc">{obj.description}</div>
                          <div className="objective-bonus">+{obj.bonus} pts per matching event</div>
                        </div>
                      );
                    })}
                  </div>
                )
              }
            </div>
          )}

          {/* Step 4 — Set mandate */}
          {step === 4 && (
            <div className="onboarding-panel">
              <h3>Set your governing mandate</h3>
              <p className="muted">Exactly 4 governing seats · ≥1 federal · ≥1 provincial. Only governing seats score each week.</p>
              <p className="muted">Governing: {governingSeats.length} · Monitoring: {monitoringSeats.length}</p>
              <div className="row">
                <button type="button" onClick={autoBalance} disabled={!portfolio.length || savingMandate}>Auto-balance mandate</button>
              </div>
              {portfolio.length === 0
                ? <p className="muted">No portfolio — go back and assemble your cabinet first.</p>
                : <MandateEditor governingSeats={governingSeats} monitoringSeats={monitoringSeats} savingMandate={savingMandate} toggleSeat={toggleSeat} />
              }
            </div>
          )}

          <div className="row onboarding-nav">
            <button type="button" onClick={() => goToStep(step - 1)} disabled={step === 0}>Back</button>
            <button
              type="button"
              onClick={continueOnboarding}
              disabled={
                savingMandate || savingObjectives ||
                (step === 1 && !selectedScopeId) ||
                (step === 2 && !selectedCabinetId) ||
                (step === 4 && !portfolio.length)
              }
            >
              {step === STEPS.length - 1 ? "Finalise mandate" : "Continue →"}
            </button>
          </div>

          {error  && <p className="error">{error}</p>}
          {notice && <p className="muted">{notice}</p>}
        </section>
      )}

      {/* ── Today in Canadian Politics ── */}
      {selectedCabinetId && (
        <section className="card">
          <h2>Today in Canadian Politics</h2>
          {dailyDigest ? (
            <>
              <p className="muted">
                {dailyDigest.total_articles_today > 0
                  ? `${dailyDigest.total_articles_today} article${dailyDigest.total_articles_today !== 1 ? "s" : ""} ingested today`
                  : "Quiet day in Ottawa — no articles yet today"}
              </p>

              {dailyDigest.top_stories.length > 0 && (
                <>
                  <h3>Top headlines</h3>
                  <ul className="events">
                    {dailyDigest.top_stories.map((story) => (
                      <li key={story.id}>
                        <div className="event-title">{story.canonical_title}</div>
                        <div className="muted">
                          <span className="event-tag">{story.event_type}</span>
                          {story.jurisdiction}
                          <span style={{ marginLeft: "0.5rem", fontSize: "0.75rem", background: "#1a4a2e", color: "#7cf0c0", borderRadius: "4px", padding: "1px 5px", fontWeight: 600 }}>
                            ★ {story.significance.toFixed(1)}
                          </span>
                          {story.article_count > 1 && (
                            <span style={{ marginLeft: "0.4rem", fontSize: "0.75rem", color: "#b9d3ff" }}>
                              {story.article_count} articles
                            </span>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {dailyDigest.active_mps_in_news.length > 0 && (
                <>
                  <h3>Your governing MPs trending</h3>
                  <div className="row" style={{ flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem" }}>
                    {dailyDigest.active_mps_in_news.map((mp) => (
                      <span key={mp.politician_id} style={{ background: "rgba(124, 240, 192, 0.15)", border: "1px solid rgba(124, 240, 192, 0.4)", borderRadius: "8px", padding: "0.3rem 0.6rem", fontSize: "0.82rem" }}>
                        🟢 {mp.politician_name}
                        <span style={{ marginLeft: "0.35rem", opacity: 0.75 }}>{mp.article_count} art.</span>
                      </span>
                    ))}
                  </div>
                </>
              )}

              {dailyDigest.bench_alerts.length > 0 && (
                <>
                  <h3>Bench alerts</h3>
                  <div className="row" style={{ flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem" }}>
                    {dailyDigest.bench_alerts.map((mp) => (
                      <span key={mp.politician_id} style={{ background: "rgba(255, 166, 0, 0.12)", border: "1px solid rgba(255, 166, 0, 0.4)", borderRadius: "8px", padding: "0.3rem 0.6rem", fontSize: "0.82rem" }}>
                        🟡 {mp.politician_name} is in the news!
                        <span style={{ marginLeft: "0.35rem", opacity: 0.75 }}>{mp.article_count} art.</span>
                      </span>
                    ))}
                  </div>
                </>
              )}

              {dailyDigest.top_stories.length === 0 && dailyDigest.active_mps_in_news.length === 0 && dailyDigest.bench_alerts.length === 0 && (
                <p className="muted" style={{ marginTop: "0.5rem" }}>No activity to show yet — check back once today&apos;s events are ingested.</p>
              )}
            </>
          ) : (
            <p className="muted">Loading today&apos;s digest…</p>
          )}
        </section>
      )}

      {/* ── Cabinet standings ── */}
      <section className="card">
        <h2>Cabinet standings</h2>
        <div className="row">
          <label htmlFor="dash-scope">Scope</label>
          <select id="dash-scope" value={selectedScopeId} onChange={(e) => setSelectedScopeId(e.target.value)} disabled={loading || !scopes.length}>
            {scopes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button type="button" onClick={runScoring} disabled={!selectedScopeId || running}>
            {running ? "Scoring…" : "Run week scoring"}
          </button>
        </div>
        {selectedScope && <p className="muted">Format: {selectedScope.format} · Week: {selectedScope.current_week}</p>}
        {standings && standings.items.length > 0 ? (
          <table>
            <thead><tr><th>Rank</th><th>Cabinet</th><th>Points</th></tr></thead>
            <tbody>
              {standings.items.map((row) => (
                <tr key={row.cabinet_id}>
                  <td>{row.rank}</td>
                  <td>{row.cabinet_name}</td>
                  <td>{row.total_points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="muted">No standings yet — run a scoring cycle to begin.</p>}
        {error && <p className="error">{error}</p>}
      </section>

      {/* ── My cabinet: MP seat picker ── */}
      <section className="card">
        <h2>My cabinet</h2>
        <div className="row">
          <label htmlFor="dash-cabinet">Cabinet</label>
          <select id="dash-cabinet" value={selectedCabinetId} onChange={(e) => setSelectedCabinetId(e.target.value)} disabled={!cabinets.length}>
            {cabinets.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        {portfolio.length > 0
          ? (
            <MPPicker
              portfolio={portfolio}
              allMPs={allMPs}
              editingSeatSlot={editingSeatSlot}
              setEditingSeatSlot={setEditingSeatSlot}
              onAssign={assignMP}
              benchSignals={benchSignals}
            />
          )
          : <p className="muted">No portfolio loaded.</p>
        }
        {error && <p className="error">{error}</p>}
      </section>

      {/* ── Mandate configuration ── */}
      <section className="card">
        <h2>Mandate configuration</h2>
        <p className="muted">4 governing seats · ≥1 federal · ≥1 provincial · only governing seats score.</p>
        <p className="muted">Governing: {governingSeats.length} · Monitoring: {monitoringSeats.length}</p>
        <div className="row">
          <button type="button" onClick={saveMandate} disabled={!selectedCabinetId || savingMandate}>{savingMandate ? "Saving…" : "Save mandate"}</button>
          <button type="button" onClick={autoBalance} disabled={!portfolio.length || savingMandate}>Auto-balance</button>
        </div>
        {portfolio.length === 0
          ? <p className="muted">No portfolio loaded.</p>
          : <MandateEditor governingSeats={governingSeats} monitoringSeats={monitoringSeats} savingMandate={savingMandate} toggleSeat={toggleSeat} />
        }
      </section>

      {/* ── Policy objectives ── */}
      <section className="card">
        <h2>Policy objectives</h2>
        <p className="muted">
          Select up to 2 objectives. Matching parliamentary events earn bonus points on top of standard scoring.
          {" "}<strong>Selected: {selectedObjectiveIds.length} / 2</strong>
        </p>
        <div className="objective-grid">
          {policyObjectives.map((obj) => {
            const active = selectedObjectiveIds.includes(obj.id);
            return (
              <div
                key={obj.id}
                className={`objective-card${active ? " objective-active" : ""}`}
                onClick={() => toggleObjective(obj.id)}
                role="checkbox"
                aria-checked={active}
                tabIndex={0}
                onKeyDown={(e) => e.key === " " && toggleObjective(obj.id)}
              >
                <div className="objective-name">{obj.name}</div>
                <div className="muted objective-desc">{obj.description}</div>
                <div className="objective-bonus">+{obj.bonus} pts per matching event</div>
              </div>
            );
          })}
        </div>
        <div className="row" style={{ marginTop: "1rem" }}>
          <button type="button" onClick={() => void savePolicyObjectives()} disabled={savingObjectives || !selectedCabinetId}>
            {savingObjectives ? "Saving…" : "Save objectives"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      {/* ── Score ledger ── */}
      <section className="card">
        <h2>Score ledger</h2>
        {ledger.length === 0
          ? <p className="muted">No scored entries yet — run a scoring cycle to see results here.</p>
          : (
            <table>
              <thead><tr><th>Week</th><th>Event</th><th>Points</th></tr></thead>
              <tbody>
                {ledger.map((entry) => {
                  const isLeadershipChange = entry.event.includes("leadership_change");
                  const isAttribLinked = !!entry.attribution_id;
                  return (
                    <tr key={entry.id}>
                      <td>{entry.week}</td>
                      <td>
                        {entry.event}
                        {isLeadershipChange && (
                          <span style={{ marginLeft: "0.5rem", fontSize: "0.75rem", background: "#f39c12", color: "#000", borderRadius: "3px", padding: "1px 5px" }}>
                            ⚡ Leadership Change
                          </span>
                        )}
                        {isAttribLinked && (
                          <span style={{ marginLeft: "0.4rem", fontSize: "0.7rem", color: "#7cf0c0" }} title={`Attribution: ${entry.attribution_id}`}>
                            ✓
                          </span>
                        )}
                      </td>
                      <td style={{ color: entry.points < 0 ? "#ff9a9a" : "#7cf0c0", fontWeight: 600 }}>
                        {entry.points > 0 ? `+${entry.points}` : entry.points}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        }
      </section>

      {/* ── Parliamentary events ── */}
      <section className="card">
        <h2>Parliamentary events</h2>
        {events.length === 0
          ? <p className="muted">No ingested events yet — the worker ingests on the next cycle.</p>
          : (
            <ul className="events">
              {events.map((ev) => (
                <li key={ev.id}>
                  <div className="event-title">
                    {ev.url ? <a href={ev.url} target="_blank" rel="noreferrer">{ev.title}</a> : ev.title}
                  </div>
                  <div className="muted">
                    <span className="event-tag">{ev.event_type}</span>
                    {" "}{ev.jurisdiction} · {ev.source_name}
                  </div>
                </li>
              ))}
            </ul>
          )
        }
      </section>

      {notice && <p className="muted" style={{ marginTop: "1rem" }}>{notice}</p>}
    </main>
  );
}

// ── MP Picker component ───────────────────────────────────────────────────────

function jurisdictionHintForSlot(slot: string): string | null {
  if (slot === "head_of_government" || slot.startsWith("federal")) return "federal";
  return null;
}

function MPPicker({
  portfolio, allMPs, editingSeatSlot, setEditingSeatSlot, onAssign, benchSignals = [],
}: {
  portfolio: PortfolioSeat[];
  allMPs: MP[];
  editingSeatSlot: string | null;
  setEditingSeatSlot: (slot: string | null) => void;
  onAssign: (slot: string, mpId: string) => Promise<void>;
  benchSignals?: BenchSignal[];
}) {
  const signalByPoliticianId = useMemo(
    () => Object.fromEntries(benchSignals.map((s) => [s.politician_id, s])),
    [benchSignals],
  );
  return (
    <div style={{ marginTop: "1rem" }}>
      <table>
        <thead>
          <tr><th>Seat</th><th>Politician</th><th>Role</th><th>Party</th><th>Jurisdiction</th><th></th></tr>
        </thead>
        <tbody>
          {portfolio.map((seat) => {
            const editing = editingSeatSlot === seat.slot;
            const hint    = jurisdictionHintForSlot(seat.slot);
            const signal  = seat.lineup_status === "bench" ? signalByPoliticianId[seat.asset_id] : undefined;
            // Filter out pending/retired for assignment; keep ineligible visible (with badge)
            const options = (hint
              ? allMPs.filter((m) => m.jurisdiction.toLowerCase() === hint)
              : allMPs
            ).filter((m) => m.status !== "pending" && m.status !== "retired");
            return (
              <Fragment key={seat.roster_slot_id}>
                <tr>
                  <td>{seat.slot_label}</td>
                  <td>
                    {seat.asset_name}
                    {signal && signal.article_count > 0 && (
                      <span
                        title={signal.top_story_title ?? "Active in news today"}
                        style={{ marginLeft: "0.4rem", fontSize: "0.72rem", background: "rgba(255,166,0,0.2)", color: "#ffa600", border: "1px solid rgba(255,166,0,0.4)", borderRadius: "4px", padding: "1px 5px", fontWeight: 600, cursor: "default" }}
                      >
                        📰 {signal.article_count}
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: "0.8rem", color: "var(--muted)" }}>{seat.asset_type}</td>
                  <td><PartyBadge party={seat.party} /></td>
                  <td>{seat.jurisdiction}</td>
                  <td>
                    <button type="button" onClick={() => setEditingSeatSlot(editing ? null : seat.slot)}>
                      {editing ? "Cancel" : "Change"}
                    </button>
                  </td>
                </tr>
                {editing && (
                  <tr>
                    <td colSpan={6}>
                      <div className="mp-picker-row">
                        <span className="muted">{hint ? `${hint.toUpperCase()} politicians` : `All politicians`} ({options.length})</span>
                        <select
                          defaultValue=""
                          onChange={(e) => { if (e.target.value) void onAssign(seat.slot, e.target.value); }}
                        >
                          <option value="" disabled>Select a politician…</option>
                          {options.map((mp) => (
                            <option
                              key={mp.id}
                              value={mp.id}
                              disabled={mp.status === "ineligible"}
                              style={mp.status === "ineligible" ? { color: "#7f8c8d" } : undefined}
                            >
                              {mp.full_name} · {mp.current_role || mp.party} · {mp.jurisdiction}
                              {mp.status === "ineligible" ? " ⚠ Ineligible" : ""}
                            </option>
                          ))}
                        </select>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Mandate editor component ──────────────────────────────────────────────────

const PARTY_COLOURS_CONST: Record<string, string> = {
  Liberal: "#c0392b", Conservative: "#2980b9", NDP: "#e67e22",
  Bloc: "#8e44ad", CAQ: "#16a085", PQ: "#2471a3",
  UCP: "#cb4335", Green: "#27ae60", independent: "#7f8c8d",
};

function MandateEditor({
  governingSeats, monitoringSeats, savingMandate, toggleSeat,
}: {
  governingSeats: PortfolioSeat[];
  monitoringSeats: PortfolioSeat[];
  savingMandate: boolean;
  toggleSeat: (id: number, governing: boolean) => void;
}) {
  function SeatTable({ seats, isGoverning }: { seats: PortfolioSeat[]; isGoverning: boolean }) {
    return (
      <table>
        <thead><tr><th>Position</th><th>MP</th><th>Party</th><th>Action</th></tr></thead>
        <tbody>
          {seats.map((s) => (
            <tr key={s.roster_slot_id}>
              <td>{s.slot_label}</td>
              <td>{s.asset_name}</td>
              <td>
                <span className="party-badge" style={{ background: PARTY_COLOURS_CONST[s.party] ?? PARTY_COLOURS_CONST.independent }}>
                  {s.party}
                </span>
              </td>
              <td>
                <button
                  type="button"
                  onClick={() => toggleSeat(s.roster_slot_id, !isGoverning)}
                  disabled={savingMandate || (isGoverning && governingSeats.length <= 1)}
                >
                  {isGoverning ? "Move to monitoring" : "Move to governing"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <div className="grid-two">
      <div>
        <h3>Governing seats</h3>
        <SeatTable seats={governingSeats} isGoverning={true} />
      </div>
      <div>
        <h3>Monitoring seats</h3>
        <SeatTable seats={monitoringSeats} isGoverning={false} />
      </div>
    </div>
  );
}
