"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

type UserProfile = {
  id: string;
  display_name: string;
  roles: string[];
};

type SystemConfigEntry = {
  key: string;
  value: string;
};

type PoliticianOut = {
  id: string;
  full_name: string;
  current_role: string;
  role_tier: number;
  party: string;
  jurisdiction: string;
  asset_type: string;
  status: string;
  aliases: string[];
  source: string;
  last_verified_at: string | null;
};

type NewsStoryOut = {
  id: string;
  canonical_title: string;
  event_type: string;
  jurisdiction: string;
  significance: number;
  sentiment: number;
  is_followup: boolean;
  article_count: number;
  status: string;
  scored: boolean;
  scored_week: number | null;
  rescore_pending: boolean;
  rescore_count: number;
  first_seen_at: string;
};

type DataSource = {
  id: string;
  name: string;
  url: string;
  jurisdiction: string;
  feed_type: string;
  is_active: boolean;
  last_fetched_at: string | null;
  article_count: number;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API = `${apiBase}/api/v1`;

const COMMISSIONER_HEADERS = {
  "Content-Type": "application/json",
  "X-Auth-Roles": "commissioner",
  "X-Auth-Sub": "admin-ui",
};

const PARTY_COLOURS: Record<string, string> = {
  Liberal: "#c0392b",
  Conservative: "#2980b9",
  NDP: "#e67e22",
  Bloc: "#8e44ad",
  CAQ: "#16a085",
  PQ: "#2471a3",
  UCP: "#cb4335",
  Green: "#27ae60",
  independent: "#7f8c8d",
};

const JURISDICTIONS = [
  "federal", "ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "NT", "NU", "YT",
];

const ASSET_TYPES = ["executive", "cabinet", "parliamentary", "opposition"];

const PARTIES = [
  "Liberal", "Conservative", "NDP", "Bloc", "Green", "CAQ", "PQ", "UCP", "independent",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: COMMISSIONER_HEADERS,
    ...init,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json() as { detail?: string };
      msg = j.detail ?? msg;
    } catch { /**/ }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

function Badge({ label, colour }: { label: string; colour?: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.12rem 0.45rem",
        borderRadius: "999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        background: colour ?? "rgba(138,180,255,0.18)",
        color: colour ? "#fff" : "#b9d3ff",
        letterSpacing: "0.02em",
      }}
    >
      {label}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colours: Record<string, string> = {
    active: "#27ae60",
    pending: "#e67e22",
    ineligible: "#7f8c8d",
    retired: "#7f8c8d",
    settling: "#e67e22",
    archived: "#555",
  };
  return <Badge label={status} colour={colours[status] ?? "#555"} />;
}

function Notice({ msg, error }: { msg: string; error?: boolean }) {
  if (!msg) return null;
  return (
    <p
      style={{
        margin: "0.5rem 0 0",
        color: error ? "#ff9a9a" : "#7cf0c0",
        fontSize: "0.875rem",
      }}
    >
      {msg}
    </p>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h2
      style={{
        fontSize: "1.1rem",
        fontWeight: 700,
        margin: "0 0 0.75rem",
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: "#b9d3ff",
        borderBottom: "1px solid rgba(138,180,255,0.25)",
        paddingBottom: "0.4rem",
      }}
    >
      {title}
    </h2>
  );
}

// ── System Config panel ───────────────────────────────────────────────────────

function SystemConfigPanel() {
  const [config, setConfig] = useState<SystemConfigEntry[]>([]);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { void load(); }, []);

  async function load() {
    try {
      const r = await apiFetch<{ config: Record<string, unknown> }>("/admin/config");
      setConfig(Object.entries(r.config).map(([key, value]) => ({ key, value: String(value) })));
    } catch (e) {
      setErr(`Could not load config: ${(e as Error).message}`);
    }
  }

  async function save(key: string) {
    const value = editing[key];
    if (value === undefined) return;
    setSaving(key);
    setMsg(""); setErr("");
    try {
      const r = await apiFetch<{ config: Record<string, unknown> }>("/admin/config", {
        method: "PATCH",
        body: JSON.stringify({ key, value }),
      });
      setConfig(Object.entries(r.config).map(([k, v]) => ({ key: k, value: String(v) })));
      setEditing((prev) => { const n = { ...prev }; delete n[key]; return n; });
      setMsg(`Saved ${key}`);
    } catch (e) {
      setErr(`Save failed: ${(e as Error).message}`);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="card">
      <SectionHeader title="System Config" />
      <table>
        <thead>
          <tr>
            <th>Key</th>
            <th>Value</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {config.map((c) => (
            <tr key={c.key}>
              <td style={{ fontFamily: "monospace", fontSize: "0.85rem" }}>{c.key}</td>
              <td>
                <input
                  value={editing[c.key] ?? c.value}
                  onChange={(e) =>
                    setEditing((prev) => ({ ...prev, [c.key]: e.target.value }))
                  }
                  style={{ minWidth: 0, width: "100%" }}
                />
              </td>
              <td>
                {editing[c.key] !== undefined && editing[c.key] !== c.value && (
                  <button
                    type="button"
                    disabled={saving === c.key}
                    onClick={() => void save(c.key)}
                  >
                    {saving === c.key ? "Saving…" : "Save"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Notice msg={msg} />
      <Notice msg={err} error />
    </div>
  );
}

// ── Bootstrap panel ───────────────────────────────────────────────────────────

function BootstrapPanel({ onPoliticiansChanged }: { onPoliticiansChanged: () => void }) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ politicians_upserted: number } | null>(null);
  const [err, setErr] = useState("");

  async function run() {
    setRunning(true); setResult(null); setErr("");
    try {
      const r = await apiFetch<{ politicians_upserted: number }>("/admin/bootstrap/run", { method: "POST" });
      setResult(r);
      onPoliticiansChanged();
    } catch (e) {
      setErr(`Bootstrap failed: ${(e as Error).message}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="card">
      <SectionHeader title="Bootstrap Engine" />
      <p className="muted" style={{ margin: "0 0 0.75rem", fontSize: "0.875rem" }}>
        Fetch politicians from configured data sources (Wikipedia, OpenParliament, etc.). Only works
        when the API container can reach external networks.
      </p>
      <div className="row">
        <button type="button" disabled={running} onClick={() => void run()}>
          {running ? "Running…" : "▶ Run bootstrap"}
        </button>
        {result && (
          <span style={{ color: "#7cf0c0", fontSize: "0.9rem" }}>
            ✓ {result.politicians_upserted} politicians upserted
          </span>
        )}
      </div>
      <Notice msg={err} error />
    </div>
  );
}

// ── Manual politician creation form ──────────────────────────────────────────

function AddPoliticianForm({ onCreated }: { onCreated: (p: PoliticianOut) => void }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({
    full_name: "",
    current_role: "",
    role_tier: "5",
    party: "Liberal",
    jurisdiction: "federal",
    asset_type: "parliamentary",
    status: "active",
    aliases_raw: "",
  });

  function set(key: string, val: string) {
    setForm((prev) => ({ ...prev, [key]: val }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setErr("");
    try {
      const aliases = form.aliases_raw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const pol = await apiFetch<PoliticianOut>("/admin/politicians", {
        method: "POST",
        body: JSON.stringify({
          full_name: form.full_name.trim(),
          current_role: form.current_role.trim(),
          role_tier: parseInt(form.role_tier, 10),
          party: form.party,
          jurisdiction: form.jurisdiction,
          asset_type: form.asset_type,
          status: form.status,
          aliases,
          source: "admin",
        }),
      });
      onCreated(pol);
      setForm({
        full_name: "", current_role: "", role_tier: "5",
        party: "Liberal", jurisdiction: "federal",
        asset_type: "parliamentary", status: "active", aliases_raw: "",
      });
      setOpen(false);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} style={{ marginBottom: "0.75rem" }}>
        + Add politician manually
      </button>
    );
  }

  return (
    <form
      onSubmit={(e) => void submit(e)}
      className="card"
      style={{ margin: "0 0 1rem", padding: "1rem 1.25rem" }}
    >
      <h3 style={{ margin: "0 0 0.75rem" }}>New politician</h3>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
          gap: "0.6rem 1rem",
        }}
      >
        <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
          Full name *
          <input
            required
            minLength={2}
            value={form.full_name}
            onChange={(e) => set("full_name", e.target.value)}
            placeholder="e.g. Mark Carney"
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
          Current role
          <input
            value={form.current_role}
            onChange={(e) => set("current_role", e.target.value)}
            placeholder="e.g. Prime Minister"
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
          Party
          <select value={form.party} onChange={(e) => set("party", e.target.value)}>
            {PARTIES.map((p) => <option key={p}>{p}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
          Jurisdiction
          <select value={form.jurisdiction} onChange={(e) => set("jurisdiction", e.target.value)}>
            {JURISDICTIONS.map((j) => <option key={j}>{j}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
          Asset type
          <select value={form.asset_type} onChange={(e) => set("asset_type", e.target.value)}>
            {ASSET_TYPES.map((a) => <option key={a}>{a}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
          Role tier (1 = PM, 5 = backbench)
          <input
            type="number"
            min={1}
            max={10}
            value={form.role_tier}
            onChange={(e) => set("role_tier", e.target.value)}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
          Status
          <select value={form.status} onChange={(e) => set("status", e.target.value)}>
            {["active", "pending", "ineligible", "retired"].map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
          Aliases (comma-separated)
          <input
            value={form.aliases_raw}
            onChange={(e) => set("aliases_raw", e.target.value)}
            placeholder="e.g. Carney, M. Carney"
          />
        </label>
      </div>
      <div className="row" style={{ marginTop: "0.9rem" }}>
        <button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Create politician"}
        </button>
        <button type="button" onClick={() => { setOpen(false); setErr(""); }}>
          Cancel
        </button>
      </div>
      <Notice msg={err} error />
    </form>
  );
}

// ── Politicians table ─────────────────────────────────────────────────────────

function PoliticiansPanel() {
  const [politicians, setPoliticians] = useState<PoliticianOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { void load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await apiFetch<{ items: PoliticianOut[] }>("/politicians");
      setPoliticians(r.items);
    } catch (e) {
      setErr(`Could not load politicians: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  function addOne(p: PoliticianOut) {
    setPoliticians((prev) => {
      const exists = prev.find((x) => x.id === p.id);
      return exists ? prev.map((x) => (x.id === p.id ? p : x)) : [p, ...prev];
    });
  }

  const filtered = filter.trim()
    ? politicians.filter(
        (p) =>
          p.full_name.toLowerCase().includes(filter.toLowerCase()) ||
          p.party.toLowerCase().includes(filter.toLowerCase()) ||
          p.jurisdiction.toLowerCase().includes(filter.toLowerCase()),
      )
    : politicians;

  return (
    <div className="card">
      <SectionHeader title={`Politicians (${politicians.length})`} />
      <AddPoliticianForm onCreated={addOne} />
      <div className="row" style={{ marginBottom: "0.5rem" }}>
        <input
          placeholder="Filter by name, party or jurisdiction…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ flex: 1, minWidth: 0 }}
        />
        <button type="button" onClick={() => void load()}>↺ Refresh</button>
      </div>
      {loading ? (
        <p className="muted">Loading…</p>
      ) : err ? (
        <Notice msg={err} error />
      ) : filtered.length === 0 ? (
        <p className="muted" style={{ fontSize: "0.875rem" }}>
          {politicians.length === 0
            ? "No politicians yet. Use 'Run bootstrap' or 'Add politician manually' above."
            : "No matches."}
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Role</th>
                <th>Party</th>
                <th>Jurisdiction</th>
                <th>Asset type</th>
                <th>Tier</th>
                <th>Status</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => (
                <tr key={p.id}>
                  <td>
                    <span style={{ fontWeight: 500 }}>{p.full_name}</span>
                    {p.aliases.length > 0 && (
                      <span className="muted" style={{ fontSize: "0.75rem", marginLeft: "0.4rem" }}>
                        ({p.aliases.join(", ")})
                      </span>
                    )}
                  </td>
                  <td className="muted" style={{ fontSize: "0.85rem" }}>{p.current_role || "—"}</td>
                  <td>
                    <Badge
                      label={p.party}
                      colour={PARTY_COLOURS[p.party] ?? PARTY_COLOURS.independent}
                    />
                  </td>
                  <td style={{ fontSize: "0.85rem" }}>{p.jurisdiction}</td>
                  <td style={{ fontSize: "0.85rem" }}>{p.asset_type}</td>
                  <td style={{ fontSize: "0.85rem", textAlign: "center" }}>{p.role_tier}</td>
                  <td><StatusBadge status={p.status} /></td>
                  <td className="muted" style={{ fontSize: "0.75rem" }}>{p.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Stories panel ─────────────────────────────────────────────────────────────

function StoriesPanel() {
  const [stories, setStories] = useState<NewsStoryOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [clustering, setClustering] = useState(false);
  const [clusterResult, setClusterResult] = useState<string>("");
  const [err, setErr] = useState("");

  useEffect(() => { void load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await apiFetch<{ items: NewsStoryOut[]; total: number }>("/stories?limit=100");
      setStories(r.items);
    } catch (e) {
      setErr(`Could not load stories: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  async function runClustering() {
    setClustering(true); setClusterResult(""); setErr("");
    try {
      const r = await apiFetch<{
        stories_created: number;
        stories_updated: number;
        articles_assigned: number;
        rescore_triggers: number;
      }>("/internal/stories/cluster", { method: "POST" });
      setClusterResult(
        `✓ ${r.stories_created} created, ${r.stories_updated} updated, ${r.articles_assigned} articles assigned, ${r.rescore_triggers} rescore triggers`,
      );
      await load();
    } catch (e) {
      setErr(`Clustering failed: ${(e as Error).message}`);
    } finally {
      setClustering(false);
    }
  }

  function sentimentColour(s: number): string {
    if (s > 0.2) return "#7cf0c0";
    if (s < -0.2) return "#ff9a9a";
    return "#b9d3ff";
  }

  return (
    <div className="card">
      <SectionHeader title={`News Stories (${stories.length})`} />
      <div className="row" style={{ marginBottom: "0.75rem" }}>
        <button type="button" disabled={clustering} onClick={() => void runClustering()}>
          {clustering ? "Clustering…" : "▶ Run story clustering"}
        </button>
        <button type="button" onClick={() => void load()}>↺ Refresh</button>
        {clusterResult && (
          <span style={{ color: "#7cf0c0", fontSize: "0.875rem" }}>{clusterResult}</span>
        )}
      </div>
      {err && <Notice msg={err} error />}
      {loading ? (
        <p className="muted">Loading…</p>
      ) : stories.length === 0 ? (
        <p className="muted" style={{ fontSize: "0.875rem" }}>
          No stories yet. Run the worker or trigger clustering above.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Jurisdiction</th>
                <th>Significance</th>
                <th>Sentiment</th>
                <th>Articles</th>
                <th>Status</th>
                <th>Scored</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {stories.map((s) => (
                <tr key={s.id}>
                  <td style={{ maxWidth: "260px" }}>
                    <span
                      title={s.canonical_title}
                      style={{
                        display: "block",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        fontSize: "0.85rem",
                        fontWeight: 500,
                      }}
                    >
                      {s.canonical_title}
                    </span>
                  </td>
                  <td>
                    <span className="event-tag">{s.event_type}</span>
                  </td>
                  <td style={{ fontSize: "0.85rem" }}>{s.jurisdiction}</td>
                  <td style={{ textAlign: "center", fontWeight: 600 }}>
                    {s.significance.toFixed(1)}
                    <span className="muted" style={{ fontWeight: 400 }}>/10</span>
                  </td>
                  <td
                    style={{
                      textAlign: "center",
                      color: sentimentColour(s.sentiment),
                      fontWeight: 600,
                    }}
                  >
                    {s.sentiment >= 0 ? "+" : ""}
                    {s.sentiment.toFixed(2)}
                  </td>
                  <td style={{ textAlign: "center" }}>{s.article_count}</td>
                  <td><StatusBadge status={s.status} /></td>
                  <td style={{ textAlign: "center" }}>
                    {s.scored ? (
                      <span style={{ color: "#7cf0c0" }}>✓{s.scored_week !== null ? ` w${s.scored_week}` : ""}</span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td style={{ fontSize: "0.78rem", whiteSpace: "nowrap" }}>
                    {s.is_followup && <Badge label="follow-up" />}
                    {s.rescore_pending && <Badge label="rescore" colour="#e67e22" />}
                    {s.rescore_count > 0 && (
                      <span className="muted"> ×{s.rescore_count}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Parliamentary Calendar panel ──────────────────────────────────────────────

type WeekModifier = {
  label: string;
  description: string;
  multipliers: Record<string, number>;
  asset_multipliers: Record<string, number>;
  event_type_whitelist?: string[];
};

function ParliamentaryCalendarPanel() {
  const [modifiers, setModifiers] = useState<Record<string, WeekModifier>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  // Form state for adding/editing a week modifier
  const [editWeek, setEditWeek] = useState("");
  const [editLabel, setEditLabel] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editMultipliersRaw, setEditMultipliersRaw] = useState("{}");
  const [editAssetMultipliersRaw, setEditAssetMultipliersRaw] = useState("{}");
  const [editWhitelistRaw, setEditWhitelistRaw] = useState("");
  const [formOpen, setFormOpen] = useState(false);

  useEffect(() => { void load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await apiFetch<{ config: Record<string, unknown> }>("/admin/config");
      const raw = r.config["week_modifiers"];
      if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        setModifiers(raw as Record<string, WeekModifier>);
      } else {
        setModifiers({});
      }
    } catch (e) {
      setErr(`Could not load config: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  function openAdd() {
    setEditWeek(""); setEditLabel(""); setEditDescription("");
    setEditMultipliersRaw("{}"); setEditAssetMultipliersRaw("{}"); setEditWhitelistRaw("");
    setFormOpen(true); setMsg(""); setErr("");
  }

  function openEdit(week: string, mod: WeekModifier) {
    setEditWeek(week);
    setEditLabel(mod.label);
    setEditDescription(mod.description);
    setEditMultipliersRaw(JSON.stringify(mod.multipliers ?? {}));
    setEditAssetMultipliersRaw(JSON.stringify(mod.asset_multipliers ?? {}));
    setEditWhitelistRaw((mod.event_type_whitelist ?? []).join(", "));
    setFormOpen(true); setMsg(""); setErr("");
  }

  async function saveModifier() {
    const week = editWeek.trim();
    const weekNum = Number(week);
    if (!week || !Number.isInteger(weekNum) || weekNum < 1) { setErr("Enter a valid positive integer week number."); return; }
    let multipliers: Record<string, number>;
    let asset_multipliers: Record<string, number>;
    try { multipliers = JSON.parse(editMultipliersRaw) as Record<string, number>; }
    catch (e) { setErr(`Multipliers must be valid JSON: ${(e as Error).message}`); return; }
    try { asset_multipliers = JSON.parse(editAssetMultipliersRaw) as Record<string, number>; }
    catch (e) { setErr(`Asset multipliers must be valid JSON: ${(e as Error).message}`); return; }
    const whitelist = editWhitelistRaw.trim()
      ? editWhitelistRaw.split(",").map((s) => s.trim()).filter(Boolean)
      : undefined;

    const newEntry: WeekModifier = { label: editLabel, description: editDescription, multipliers, asset_multipliers };
    if (whitelist) newEntry.event_type_whitelist = whitelist;

    const updated = { ...modifiers, [week]: newEntry };
    setSaving(true); setMsg(""); setErr("");
    try {
      await apiFetch<unknown>("/admin/config", {
        method: "PATCH",
        body: JSON.stringify({ key: "week_modifiers", value: updated }),
      });
      setModifiers(updated);
      setMsg(`Week ${week} modifier saved.`);
      setFormOpen(false);
    } catch (e) {
      setErr(`Save failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  async function deleteModifier(week: string) {
    const updated = { ...modifiers };
    delete updated[week];
    setSaving(true); setMsg(""); setErr("");
    try {
      await apiFetch<unknown>("/admin/config", {
        method: "PATCH",
        body: JSON.stringify({ key: "week_modifiers", value: updated }),
      });
      setModifiers(updated);
      setMsg(`Week ${week} modifier removed.`);
    } catch (e) {
      setErr(`Delete failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  const weekIcon = (label: string) => {
    const l = label.toLowerCase();
    if (l.includes("budget")) return "🏛️";
    if (l.includes("opposition")) return "⚔️";
    if (l.includes("prorogation")) return "🔔";
    return "📅";
  };

  return (
    <div className="card">
      <SectionHeader title="Parliamentary Calendar" />
      <p className="muted" style={{ margin: "0 0 0.75rem", fontSize: "0.875rem" }}>
        Map game weeks to special parliamentary events. Modifiers affect scoring multipliers and
        event-type whitelists during those weeks.
      </p>

      {loading ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          {Object.keys(modifiers).length === 0 ? (
            <p className="muted">No week modifiers configured yet.</p>
          ) : (
            <div style={{ overflowX: "auto", marginBottom: "1rem" }}>
              <table>
                <thead>
                  <tr>
                    <th>Week</th>
                    <th>Label</th>
                    <th>Description</th>
                    <th>Multipliers</th>
                    <th>Whitelist</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(modifiers)
                    .sort(([a], [b]) => Number(a) - Number(b))
                    .map(([week, mod]) => (
                      <tr key={week}>
                        <td style={{ fontWeight: 700, textAlign: "center" }}>{weekIcon(mod.label)} {week}</td>
                        <td style={{ fontWeight: 600, color: "#e0eaff" }}>{mod.label}</td>
                        <td style={{ fontSize: "0.82rem", color: "rgba(185,211,255,0.8)", maxWidth: "220px" }}>{mod.description}</td>
                        <td style={{ fontSize: "0.8rem" }}>
                          {Object.entries(mod.multipliers ?? {}).map(([k, v]) => (
                            <span key={k} style={{ display: "inline-block", marginRight: "0.3rem", background: "rgba(124,240,192,0.12)", borderRadius: "3px", padding: "0 5px", color: "#7cf0c0" }}>
                              {k} ×{v}
                            </span>
                          ))}
                          {Object.entries(mod.asset_multipliers ?? {}).map(([k, v]) => (
                            <span key={k} style={{ display: "inline-block", marginRight: "0.3rem", background: "rgba(255,200,100,0.1)", borderRadius: "3px", padding: "0 5px", color: "#ffd97d" }}>
                              {k} ×{v}
                            </span>
                          ))}
                        </td>
                        <td style={{ fontSize: "0.8rem", color: "#ff9a9a" }}>
                          {mod.event_type_whitelist ? mod.event_type_whitelist.join(", ") : "—"}
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: "0.4rem" }}>
                            <button type="button" onClick={() => openEdit(week, mod)} disabled={saving} style={{ fontSize: "0.8rem", padding: "0.2rem 0.6rem" }}>Edit</button>
                            <button type="button" onClick={() => void deleteModifier(week)} disabled={saving} style={{ fontSize: "0.8rem", padding: "0.2rem 0.6rem", background: "rgba(255,80,80,0.15)", color: "#ff9a9a" }}>Remove</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}

          {!formOpen && (
            <button type="button" onClick={openAdd} style={{ marginTop: "0.25rem" }}>
              + Add week modifier
            </button>
          )}

          {formOpen && (
            <div className="card" style={{ margin: "1rem 0 0", padding: "1rem 1.25rem", background: "rgba(24,48,80,0.6)" }}>
              <h3 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>
                {editWeek && modifiers[editWeek] ? `Edit Week ${editWeek} Modifier` : "New Week Modifier"}
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "0.6rem 1rem" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
                  Week number *
                  <input
                    type="number"
                    min={1}
                    value={editWeek}
                    onChange={(e) => setEditWeek(e.target.value)}
                    placeholder="e.g. 3"
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
                  Label *
                  <input value={editLabel} onChange={(e) => setEditLabel(e.target.value)} placeholder="e.g. Budget Week" />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem", gridColumn: "span 2" }}>
                  Description
                  <input value={editDescription} onChange={(e) => setEditDescription(e.target.value)} placeholder="Brief description shown in the banner" />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
                  Event-type multipliers (JSON)
                  <input value={editMultipliersRaw} onChange={(e) => setEditMultipliersRaw(e.target.value)} placeholder={'{\"policy\": 1.5}'} style={{ fontFamily: "monospace", fontSize: "0.82rem" }} />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
                  Asset-type multipliers (JSON)
                  <input value={editAssetMultipliersRaw} onChange={(e) => setEditAssetMultipliersRaw(e.target.value)} placeholder={'{\"opposition\": 1.5}'} style={{ fontFamily: "monospace", fontSize: "0.82rem" }} />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.85rem" }}>
                  Event-type whitelist (comma-separated, blank = all)
                  <input value={editWhitelistRaw} onChange={(e) => setEditWhitelistRaw(e.target.value)} placeholder="parliamentary, intergovernmental" />
                </label>
              </div>
              <div className="row" style={{ marginTop: "0.75rem", gap: "0.5rem" }}>
                <button type="button" onClick={() => void saveModifier()} disabled={saving}>
                  {saving ? "Saving…" : "Save modifier"}
                </button>
                <button type="button" onClick={() => { setFormOpen(false); setErr(""); }} disabled={saving} style={{ background: "rgba(255,255,255,0.06)" }}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      )}
      <Notice msg={msg} />
      <Notice msg={err} error />
    </div>
  );
}

// ── Data Sources panel ────────────────────────────────────────────────────────

function DataSourcesPanel() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => { void load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await apiFetch<{ items: DataSource[] }>("/internal/data-sources");
      setSources(r.items);
    } catch (e) {
      setErr(`Could not load data sources: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <SectionHeader title={`Data Sources (${sources.length})`} />
      {loading ? (
        <p className="muted">Loading…</p>
      ) : err ? (
        <Notice msg={err} error />
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Jurisdiction</th>
                <th>Type</th>
                <th>Articles</th>
                <th>Last fetched</th>
                <th>Active</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id}>
                  <td>
                    <a href={s.url} target="_blank" rel="noreferrer" style={{ fontSize: "0.875rem" }}>
                      {s.name}
                    </a>
                  </td>
                  <td style={{ fontSize: "0.85rem" }}>{s.jurisdiction}</td>
                  <td>
                    <span className="event-tag">{s.feed_type}</span>
                  </td>
                  <td style={{ textAlign: "center" }}>{s.article_count}</td>
                  <td className="muted" style={{ fontSize: "0.8rem" }}>
                    {s.last_fetched_at
                      ? new Date(s.last_fetched_at).toLocaleString()
                      : "never"}
                  </td>
                  <td style={{ textAlign: "center" }}>
                    {s.is_active ? (
                      <span style={{ color: "#7cf0c0" }}>✓</span>
                    ) : (
                      <span style={{ color: "#ff9a9a" }}>✗</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main admin page ───────────────────────────────────────────────────────────

export default function AdminPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [activeTab, setActiveTab] = useState<"politicians" | "stories" | "sources" | "config" | "calendar">(
    "politicians",
  );

  useEffect(() => { void loadProfile(); }, []);

  async function loadProfile() {
    try {
      const p = await fetch(`${API}/auth/me`, { headers: COMMISSIONER_HEADERS });
      if (p.ok) {
        const data = await p.json() as UserProfile;
        setProfile(data);
      }
    } catch { /**/ }
    setAuthChecked(true);
  }

  const isCommissioner =
    !authChecked ||
    !profile ||
    profile.roles.includes("commissioner") ||
    profile.roles.includes("admin");

  if (!authChecked) {
    return (
      <main>
        <p className="muted">Checking authorization…</p>
      </main>
    );
  }

  if (!isCommissioner) {
    return (
      <main>
        <h1>Admin Centre</h1>
        <p className="error">You need the commissioner role to access this page.</p>
        <Link href="/">← Back to game</Link>
      </main>
    );
  }

  const tabs: { id: typeof activeTab; label: string }[] = [
    { id: "politicians", label: "Politicians" },
    { id: "stories", label: "News Stories" },
    { id: "sources", label: "Data Sources" },
    { id: "config", label: "System Config" },
    { id: "calendar", label: "📅 Parliamentary Calendar" },
  ];

  return (
    <main style={{ maxWidth: "1100px" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "1.5rem",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: "1.6rem", fontWeight: 800 }}>
            🍁 Commissioner Admin Centre
          </h1>
          {profile && (
            <p className="muted" style={{ margin: "0.2rem 0 0", fontSize: "0.85rem" }}>
              Signed in as {profile.display_name} &middot; roles: {profile.roles.join(", ")}
            </p>
          )}
        </div>
        <Link href="/" style={{ fontSize: "0.875rem" }}>← Back to game</Link>
      </div>

      {/* Bootstrap at top — always visible */}
      <BootstrapPanel onPoliticiansChanged={() => { /**/ }} />

      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          gap: "0.25rem",
          marginTop: "1.5rem",
          marginBottom: "-1px",
        }}
      >
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActiveTab(t.id)}
            style={{
              borderBottomLeftRadius: 0,
              borderBottomRightRadius: 0,
              borderBottom: activeTab === t.id ? "2px solid #b9d3ff" : "2px solid transparent",
              background:
                activeTab === t.id
                  ? "rgba(138,180,255,0.15)"
                  : "rgba(255,255,255,0.04)",
              color: activeTab === t.id ? "#fff" : "#b9d3ff",
              padding: "0.4rem 0.9rem",
              fontWeight: activeTab === t.id ? 700 : 400,
              fontSize: "0.9rem",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "politicians" && <PoliticiansPanel />}
      {activeTab === "stories" && <StoriesPanel />}
      {activeTab === "sources" && <DataSourcesPanel />}
      {activeTab === "config" && <SystemConfigPanel />}
      {activeTab === "calendar" && <ParliamentaryCalendarPanel />}
    </main>
  );
}
