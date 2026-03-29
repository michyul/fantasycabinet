"use client";

import { useEffect, useMemo, useState } from "react";
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
  participation_streak: number;
  positive_streak: number;
};

type StandingsResponse = {
  scope_id: string;
  week: number;
  items: StandingsRow[];
};

type AchievementOut = {
  id: string;
  team_id: string;
  achievement_id: string;
  name: string;
  description: string;
  earned_at: string;
  week: number;
  metadata: Record<string, unknown>;
};

type ManagerStatsOut = {
  team_id: string;
  participation_streak: number;
  positive_streak: number;
  longest_participation_streak: number;
  longest_positive_streak: number;
  updated_at?: string | null;
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

type WeekTheme = {
  week: number;
  label: string;
  description: string;
  multipliers: Record<string, number>;
  asset_multipliers: Record<string, number>;
  event_type_whitelist: string[] | null;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const ONBOARDING_KEY = "fc_onboarding_v4";

const RANK_MEDALS = ["🥇", "🥈", "🥉"];

const OBJECTIVE_ICONS: Record<string, string> = {
  economy: "💰", budget: "💰", fiscal: "💰",
  health: "🏥", healthcare: "🏥",
  climate: "🌿", environment: "🌿", green: "🌿",
  justice: "⚖️", law: "⚖️", legal: "⚖️",
  housing: "🏠",
  transit: "🚆", transport: "🚆", infrastructure: "🏗️",
  defense: "🛡️", security: "🛡️",
  foreign: "🌐", international: "🌐",
  indigenous: "🪶", reconciliation: "🪶",
  education: "📚",
  energy: "⚡",
  trade: "🤝",
  agriculture: "🌾",
};

function getObjectiveIcon(name: string): string {
  const lower = name.toLowerCase();
  for (const [key, icon] of Object.entries(OBJECTIVE_ICONS)) {
    if (lower.includes(key)) return icon;
  }
  return "📋";
}

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
  const [weekTheme, setWeekTheme]                       = useState<WeekTheme | null>(null);
  const [achievements, setAchievements]                 = useState<AchievementOut[]>([]);
  const [cabinetStats, setCabinetStats]                 = useState<ManagerStatsOut | null>(null);

  const governingSeats  = portfolio.filter((s) => s.lineup_status === "active");
  const monitoringSeats = portfolio.filter((s) => s.lineup_status === "bench");
  const selectedScope   = useMemo(() => scopes.find((s) => s.id === selectedScopeId), [scopes, selectedScopeId]);
  const myCabinets      = useMemo(
    () => profile ? cabinets.filter((c) => c.manager_user_id === profile.id) : cabinets,
    [cabinets, profile],
  );
  const myCabinetIds    = useMemo(() => new Set(myCabinets.map((c) => c.id)), [myCabinets]);
  const maxStandingsPts = standings ? Math.max(...standings.items.map((r) => r.total_points), 1) : 1;
  const mandateValid    = governingSeats.length === 4 &&
    governingSeats.some((s) => s.jurisdiction.toLowerCase() === "federal") &&
    governingSeats.some((s) => s.jurisdiction.toLowerCase() !== "federal");
  const ledgerByWeek    = useMemo(() => {
    const groups = new Map<number, LedgerEntry[]>();
    for (const entry of ledger) {
      const arr = groups.get(entry.week) ?? [];
      arr.push(entry);
      groups.set(entry.week, arr);
    }
    return [...groups.entries()].sort((a, b) => b[0] - a[0]);
  }, [ledger]);
  const weekTotals      = useMemo(
    () => Object.fromEntries(ledgerByWeek.map(([week, entries]) => [week, entries.reduce((sum, e) => sum + e.points, 0)])),
    [ledgerByWeek],
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

  async function loadWeekTheme(scopeId: string) {
    if (!scopeId) { setWeekTheme(null); return; }
    try {
      const b = await readJson<WeekTheme | null>(`${apiBase}/api/v1/cabinet-scopes/${scopeId}/week-theme`);
      setWeekTheme(b);
    } catch { setWeekTheme(null); }
  }

  async function loadAchievements(cabinetId: string) {
    if (!cabinetId) { setAchievements([]); return; }
    try {
      const b = await readJson<{ items: AchievementOut[] }>(`${apiBase}/api/v1/cabinets/${cabinetId}/achievements`);
      setAchievements(b.items);
    } catch { setAchievements([]); }
  }

  async function loadCabinetStats(cabinetId: string) {
    if (!cabinetId) { setCabinetStats(null); return; }
    try {
      const b = await readJson<ManagerStatsOut>(`${apiBase}/api/v1/cabinets/${cabinetId}/stats`);
      setCabinetStats(b);
    } catch { setCabinetStats(null); }
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
      void loadWeekTheme(selectedScopeId);
    }
  }, [selectedScopeId, profile?.id]);

  useEffect(() => {
    if (selectedCabinetId) {
      void loadPortfolio(selectedCabinetId);
      void loadCabinetObjectives(selectedCabinetId);
      void loadDailyDigest(selectedCabinetId);
      void loadBenchSignals(selectedCabinetId);
      void loadAchievements(selectedCabinetId);
      void loadCabinetStats(selectedCabinetId);
      if (selectedScopeId) void loadLedger(selectedCabinetId, selectedScopeId);
    }
  }, [selectedCabinetId, selectedScopeId]);

  if (!hydrated) return <main><h1>🍁 FantasyCabinet</h1><p className="muted">Loading…</p></main>;

  // ── render ────────────────────────────────────────────────────────────────

  const isCommissioner = profile?.roles.includes("commissioner") || profile?.roles.includes("admin");

  return (
    <>
      <header className="app-header">
        <div className="app-header-inner">
          <div className="brand">
            <span className="brand-maple" aria-hidden="true">🍁</span>
            <span className="brand-name">FantasyCabinet</span>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            {profile && (
              <div className="profile-chip">
                <span className="profile-avatar" aria-label={profile.display_name}>{profile.display_name[0]?.toUpperCase()}</span>
                <span>{profile.display_name}</span>
              </div>
            )}
            {isCommissioner && <a href="/admin" className="admin-link">⚙ Admin</a>}
          </div>
        </div>
      </header>
      <main>
      <p className="muted" style={{ marginBottom: "1.25rem" }}>Build a cabinet of Canadian MPs, set your governing mandate, and score from real parliamentary events.</p>

      {/* ── Week Theme Banner ── */}
      {weekTheme && (
        <section style={{
          background: "linear-gradient(135deg, rgba(24,48,80,0.95), rgba(16,36,64,0.98))",
          border: "1px solid rgba(138,180,255,0.35)",
          borderRadius: "10px",
          padding: "0.9rem 1.25rem",
          marginBottom: "1rem",
          display: "flex",
          alignItems: "flex-start",
          gap: "0.75rem",
        }}>
          <span style={{ fontSize: "1.5rem", lineHeight: 1 }}>
            {weekTheme.label.toLowerCase().includes("budget") ? "🏛️" :
             weekTheme.label.toLowerCase().includes("opposition") ? "⚔️" :
             weekTheme.label.toLowerCase().includes("prorogation") ? "🔔" : "📅"}
          </span>
          <div>
            <div style={{ fontWeight: 700, fontSize: "1rem", color: "#e0eaff", marginBottom: "0.2rem" }}>
              Week {weekTheme.week}: {weekTheme.label}
            </div>
            <div style={{ fontSize: "0.875rem", color: "rgba(185,211,255,0.85)" }}>
              {weekTheme.description}
            </div>
            {(Object.keys(weekTheme.multipliers).length > 0 || Object.keys(weekTheme.asset_multipliers).length > 0) && (
              <div style={{ marginTop: "0.4rem", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                {Object.entries(weekTheme.multipliers).map(([type, mult]) => (
                  <span key={type} style={{ background: "rgba(124,240,192,0.15)", border: "1px solid rgba(124,240,192,0.35)", borderRadius: "4px", padding: "1px 7px", fontSize: "0.78rem", color: "#7cf0c0" }}>
                    {type} ×{mult}
                  </span>
                ))}
                {Object.entries(weekTheme.asset_multipliers).map(([type, mult]) => (
                  <span key={type} style={{ background: "rgba(255,200,100,0.12)", border: "1px solid rgba(255,200,100,0.35)", borderRadius: "4px", padding: "1px 7px", fontSize: "0.78rem", color: "#ffd97d" }}>
                    {type} ×{mult}
                  </span>
                ))}
                {weekTheme.event_type_whitelist && (
                  <span style={{ background: "rgba(255,120,120,0.12)", border: "1px solid rgba(255,120,120,0.35)", borderRadius: "4px", padding: "1px 7px", fontSize: "0.78rem", color: "#ff9a9a" }}>
                    only: {weekTheme.event_type_whitelist.join(", ")}
                  </span>
                )}
              </div>
            )}
          </div>
        </section>
      )}

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
                  {dailyDigest.top_stories.map((story) => (
                    <div key={story.id} className="story-card">
                      <div className="story-title">{story.canonical_title}</div>
                      <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap", alignItems: "center" }}>
                        <span className="event-tag">{story.event_type}</span>
                        <span style={{ fontSize: "0.78rem", color: "rgba(185,211,255,0.6)" }}>{story.jurisdiction}</span>
                        {story.article_count > 1 && (
                          <span style={{ fontSize: "0.75rem", color: "#b9d3ff" }}>{story.article_count} articles</span>
                        )}
                        <span style={{ marginLeft: "auto", fontSize: "0.72rem", color: "#7cf0c0", fontWeight: 600 }}>
                          ★ {story.significance.toFixed(1)}
                        </span>
                      </div>
                      <div className="story-sig-bar">
                        <div className="story-sig-fill" style={{ width: `${(story.significance / 10) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </>
              )}

              {dailyDigest.active_mps_in_news.length > 0 && (
                <>
                  <h3>Your governing MPs trending</h3>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem", marginTop: "0.5rem" }}>
                    {dailyDigest.active_mps_in_news.map((mp) => (
                      <span key={mp.politician_id} className="active-mp-pill">
                        🟢 <span className="active-mp-pill-name">{mp.politician_name}</span>
                        <span style={{ opacity: 0.7, fontSize: "0.78rem" }}>{mp.article_count} art.</span>
                      </span>
                    ))}
                  </div>
                </>
              )}

              {dailyDigest.bench_alerts.length > 0 && (
                <>
                  <h3>Bench alerts</h3>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem", marginTop: "0.5rem" }}>
                    {dailyDigest.bench_alerts.map((mp) => (
                      <span key={mp.politician_id} className="bench-signal-pill">
                        🟡 <span className="bench-signal-name">{mp.politician_name}</span>
                        <span style={{ opacity: 0.7, fontSize: "0.78rem" }}>{mp.article_count} art.</span>
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
        <div className="section-head">
          <h2>Cabinet standings</h2>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <select id="dash-scope" value={selectedScopeId} onChange={(e) => setSelectedScopeId(e.target.value)} disabled={loading || !scopes.length}>
              {scopes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <button type="button" onClick={runScoring} disabled={!selectedScopeId || running}>
              {running ? "Scoring…" : "⚡ Run scoring"}
            </button>
          </div>
        </div>
        {selectedScope && <p className="muted" style={{ marginTop: "0.25rem" }}>Format: {selectedScope.format} · Week {selectedScope.current_week}</p>}
        {standings && standings.items.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Cabinet</th>
                <th>Points</th>
                <th title="Consecutive weeks with a mandate change">🗳 Streak</th>
                <th title="Consecutive weeks with positive score">📈 Streak</th>
              </tr>
            </thead>
            <tbody>
              {standings.items.map((row) => (
                <tr key={row.cabinet_id}>
                  <td>{row.rank}</td>
                  <td>{row.cabinet_name}</td>
                  <td>{row.total_points}</td>
                  <td>
                    {row.participation_streak > 0
                      ? <span aria-label={`${row.participation_streak}-week active mandate streak`} title={`${row.participation_streak}-week active mandate streak`}>🗳 {row.participation_streak}</span>
                      : <span className="muted" aria-label="No active mandate streak">—</span>}
                  </td>
                  <td>
                    {row.positive_streak > 0
                      ? <span aria-label={`${row.positive_streak}-week positive score streak`} title={`${row.positive_streak}-week positive score streak`}>📈 {row.positive_streak}</span>
                      : <span className="muted" aria-label="No positive score streak">—</span>}
                  </td>
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
        <div className="section-head">
          <h2>Mandate configuration</h2>
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <button type="button" onClick={autoBalance} disabled={!portfolio.length || savingMandate}>Auto-balance</button>
            <button type="button" onClick={saveMandate} disabled={!selectedCabinetId || savingMandate}>{savingMandate ? "Saving…" : "Save mandate"}</button>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "0.25rem" }}>Click a seat to toggle governing ↔ bench. Need exactly 4 governing, ≥1 federal, ≥1 provincial.</p>
        <div className="stats-bar">
          <div className="stat-chip stat-chip--green">
            <span className="stat-chip-value">{governingSeats.length}</span>
            <span className="stat-chip-label">Governing</span>
          </div>
          <div className="stat-chip stat-chip--blue">
            <span className="stat-chip-value">{monitoringSeats.length}</span>
            <span className="stat-chip-label">Monitoring</span>
          </div>
          <div className={`stat-chip ${mandateValid ? "stat-chip--green" : "stat-chip--yellow"}`}>
            <span className="stat-chip-value">{mandateValid ? "✓" : "!"}</span>
            <span className="stat-chip-label">Mandate</span>
          </div>
        </div>
        {portfolio.length === 0
          ? <p className="muted">No portfolio loaded.</p>
          : <MandateEditor governingSeats={governingSeats} monitoringSeats={monitoringSeats} savingMandate={savingMandate} toggleSeat={toggleSeat} />
        }
      </section>

      {/* ── Policy objectives ── */}
      <section className="card">
        <div className="section-head">
          <h2>Policy objectives</h2>
          <span className="muted" style={{ fontSize: "0.85rem" }}>{selectedObjectiveIds.length} / 2 selected</span>
        </div>
        <p className="muted" style={{ marginTop: "0.25rem" }}>Choose up to 2. Matching events earn bonus points on top of standard scoring.</p>
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
                <div className="objective-icon" aria-hidden="true">{getObjectiveIcon(obj.name)}</div>
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
          : ledgerByWeek.map(([week, entries]) => (
            <div key={week}>
              <div className="ledger-week-header">
                <span className="ledger-week-label">Week {week}</span>
                <span className={`ledger-week-total ${weekTotals[week] >= 0 ? "point-pos" : "point-neg"}`}>
                  {weekTotals[week] > 0 ? `+${weekTotals[week]}` : weekTotals[week]} pts
                </span>
              </div>
              {entries.map((entry) => {
                const isLeadershipChange = entry.event.includes("leadership_change");
                const isAttribLinked = !!entry.attribution_id;
                return (
                  <div key={entry.id} className="ledger-entry">
                    <span className="ledger-event">
                      {entry.event}
                      {isLeadershipChange && (
                        <span style={{ marginLeft: "0.45rem", fontSize: "0.72rem", background: "#f39c12", color: "#000", borderRadius: "3px", padding: "1px 5px" }}>
                          ⚡ Leadership
                        </span>
                      )}
                      {isAttribLinked && (
                        <span style={{ marginLeft: "0.4rem", fontSize: "0.7rem", color: "#7cf0c0" }} title={`Attribution: ${entry.attribution_id}`}>
                          ✓
                        </span>
                      )}
                    </span>
                    <span className={`ledger-points ${entry.points >= 0 ? "point-pos" : "point-neg"}`}>
                      {entry.points > 0 ? `+${entry.points}` : entry.points}
                    </span>
                  </div>
                );
              })}
            </div>
          ))
        }
      </section>

      {/* ── Achievements & streak stats ── */}
      {selectedCabinetId && (
        <section className="card">
          <h2>Achievements &amp; streaks</h2>
          {cabinetStats && (
            <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>
                  {cabinetStats.participation_streak > 0 ? `🗳 ${cabinetStats.participation_streak}` : "—"}
                </div>
                <div className="muted" style={{ fontSize: "0.75rem" }}>Mandate streak</div>
                <div className="muted" style={{ fontSize: "0.7rem" }}>Best: {cabinetStats.longest_participation_streak}</div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>
                  {cabinetStats.positive_streak > 0 ? `📈 ${cabinetStats.positive_streak}` : "—"}
                </div>
                <div className="muted" style={{ fontSize: "0.75rem" }}>Positive streak</div>
                <div className="muted" style={{ fontSize: "0.7rem" }}>Best: {cabinetStats.longest_positive_streak}</div>
              </div>
            </div>
          )}
          {achievements.length > 0 ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
              {achievements.map((ach) => (
                <div
                  key={ach.id}
                  title={`${ach.description} (Week ${ach.week})`}
                  style={{
                    background: "rgba(124,240,192,0.12)",
                    border: "1px solid rgba(124,240,192,0.35)",
                    borderRadius: "8px",
                    padding: "0.5rem 0.75rem",
                    fontSize: "0.85rem",
                    cursor: "default",
                  }}
                >
                  <span style={{ marginRight: "0.4rem" }}>🏅</span>
                  <strong>{ach.name}</strong>
                  <span className="muted" style={{ marginLeft: "0.4rem", fontSize: "0.75rem" }}>Wk {ach.week}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No achievements yet — complete scoring cycles to earn badges.</p>
          )}
        </section>
      )}

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
    </>
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
    <div className="mp-card-grid">
      {portfolio.map((seat) => {
        const editing  = editingSeatSlot === seat.slot;
        const hint     = jurisdictionHintForSlot(seat.slot);
        const signal   = seat.lineup_status === "bench" ? signalByPoliticianId[seat.asset_id] : undefined;
        const options  = (hint
          ? allMPs.filter((m) => m.jurisdiction.toLowerCase() === hint)
          : allMPs
        ).filter((m) => m.status !== "pending" && m.status !== "retired");
        const initials = seat.asset_name.split(" ").map((w) => w[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();
        const partyBg  = PARTY_COLOURS[seat.party] ?? PARTY_COLOURS.independent;
        return (
          <div key={seat.roster_slot_id} className={`mp-card${seat.lineup_status === "bench" ? " mp-card--bench" : ""}`}>
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
              <div className="mp-avatar" style={{ background: partyBg }} aria-label={`${seat.asset_name} — ${seat.party}`}>{initials}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="mp-card-name">{seat.asset_name}</div>
                <div className="mp-card-role">{seat.asset_type}</div>
                <div className="mp-card-meta">
                  <PartyBadge party={seat.party} />
                  <span style={{ fontSize: "0.78rem", color: "rgba(185,211,255,0.6)" }}>{seat.jurisdiction}</span>
                  {signal && signal.article_count > 0 && (
                    <span className="trending-hot" aria-label={signal.top_story_title ?? "Active in news today"}>
                      📰 {signal.article_count}
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="mp-card-footer">
              <span className="mp-seat-label">{seat.slot_label}</span>
              {editing ? (
                <div style={{ display: "flex", gap: "0.35rem", alignItems: "center", flex: 1, minWidth: 0 }}>
                  <select
                    style={{ flex: 1, minWidth: 0 }}
                    defaultValue=""
                    onChange={(e) => { if (e.target.value) void onAssign(seat.slot, e.target.value); }}
                  >
                    <option value="" disabled>{hint ? `${hint.toUpperCase()} (${options.length})` : `All (${options.length})`}</option>
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
                  <button type="button" onClick={() => setEditingSeatSlot(null)}>✕</button>
                </div>
              ) : (
                <button type="button" onClick={() => setEditingSeatSlot(seat.slot)}>Change</button>
              )}
            </div>
          </div>
        );
      })}
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
  const allSeats = [...governingSeats, ...monitoringSeats];
  return (
    <div className="mandate-slot-grid">
      {allSeats.map((seat) => {
        const isActive = seat.lineup_status === "active";
        const canDeactivate = !isActive || governingSeats.length > 1;
        return (
          <div
            key={seat.roster_slot_id}
            className={`mandate-slot${isActive ? " mandate-slot--active" : " mandate-slot--bench"}`}
            onClick={() => { if (!savingMandate && canDeactivate) toggleSeat(seat.roster_slot_id, !isActive); }}
            role="button"
            aria-label={`${isActive ? "Move to bench" : "Activate"}: ${seat.asset_name}`}
            aria-pressed={isActive}
            aria-disabled={savingMandate || !canDeactivate}
            tabIndex={savingMandate || !canDeactivate ? -1 : 0}
            onKeyDown={(e) => {
              if ((e.key === " " || e.key === "Enter") && !savingMandate && canDeactivate) {
                toggleSeat(seat.roster_slot_id, !isActive);
              }
            }}
          >
            <div className={`mandate-slot-status mandate-slot-status--${isActive ? "active" : "bench"}`}>
              {isActive ? "● Governing" : "○ Bench"}
            </div>
            <div className="mandate-slot-name">{seat.asset_name}</div>
            <div className="mandate-slot-label">{seat.slot_label}</div>
            <div style={{ display: "flex", gap: "0.35rem", alignItems: "center", flexWrap: "wrap", marginTop: "0.2rem" }}>
              <span className="party-badge" style={{ background: PARTY_COLOURS_CONST[seat.party] ?? PARTY_COLOURS_CONST.independent }}>
                {seat.party}
              </span>
              <span style={{ fontSize: "0.72rem", color: "rgba(185,211,255,0.45)" }}>{seat.jurisdiction}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

