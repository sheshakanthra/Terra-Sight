"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { ApiError, createField, listFields } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import type { Field, PolygonGeometry } from "@/lib/types";
import FieldDashboard from "@/components/dashboard/FieldDashboard";

// MapLibre touches `window` at module scope, so it cannot be server-rendered.
const FieldMap = dynamic(() => import("@/components/FieldMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-surface" />,
});

interface WorkspaceProps {
  session: Session;
}

export default function Workspace({ session }: WorkspaceProps) {
  const [fields, setFields] = useState<Field[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [pending, setPending] = useState<PolygonGeometry | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadFields = useCallback(async () => {
    try {
      setFields(await listFields());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Your fields could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFields();
  }, [loadFields]);

  const handlePolygonDrawn = useCallback((geometry: PolygonGeometry) => {
    setPending(geometry);
    setDrawing(false);
    setError(null);
  }, []);

  function startDrawing() {
    setSelectedId(null);
    setDrawing(true);
    setError(null);
  }

  function selectField(id: string) {
    setDrawing(false);
    setPending(null);
    setSelectedId(id);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!pending) return;
    setSaving(true);
    setError(null);
    try {
      const field = await createField(name, pending);
      setFields((current) => [field, ...current]);
      setPending(null);
      setName("");
      setSelectedId(field.id); // open the new field's dashboard
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That field could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  function cancel() {
    setPending(null);
    setName("");
    setError(null);
    setDrawing(false);
  }

  const selectedField = fields.find((f) => f.id === selectedId) ?? null;
  const showDashboard = selectedField && !drawing && !pending;

  return (
    <main className="flex h-screen flex-col md:flex-row">
      <aside className="flex w-full shrink-0 flex-col gap-4 border-border p-5 md:w-72 md:border-r">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold tracking-tight">TerraSight</h1>
          <button
            onClick={() => void supabase.auth.signOut()}
            className="readout hover:text-foreground"
          >
            Sign out
          </button>
        </div>
        <p className="truncate font-mono text-[11px] text-muted">{session.user.email}</p>

        <button
          onClick={startDrawing}
          className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
            drawing
              ? "border border-healthy text-healthy"
              : "bg-healthy text-background hover:opacity-90"
          }`}
        >
          {drawing ? "Drawing… click to place corners" : "Draw a field"}
        </button>

        {error && !showDashboard && (
          <p className="rounded-md border border-stress/40 bg-stress/10 px-3 py-2 text-sm text-stress">
            {error}
          </p>
        )}

        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
          <span className="readout">Your fields {fields.length > 0 && `· ${fields.length}`}</span>
          {loading ? (
            <p className="text-sm text-muted">Loading…</p>
          ) : fields.length === 0 ? (
            <p className="text-sm text-muted">No fields yet. Draw your first one on the map.</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {fields.map((field) => {
                const active = field.id === selectedId;
                return (
                  <li key={field.id}>
                    <button
                      onClick={() => selectField(field.id)}
                      className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
                        active
                          ? "border-healthy bg-surface"
                          : "border-border bg-surface hover:border-muted"
                      }`}
                    >
                      <p className="truncate text-sm font-medium">{field.name}</p>
                      <p className="font-mono text-[11px] text-muted tabular-nums">
                        {field.area_ha.toFixed(2)} ha
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>

      <section className="min-h-0 flex-1">
        {showDashboard ? (
          <FieldDashboard field={selectedField} />
        ) : (
          <div className="relative h-full">
            <FieldMap
              fields={fields}
              drawing={drawing}
              overlay={null}
              onPolygonDrawn={handlePolygonDrawn}
            />
            {pending && (
              <form
                onSubmit={save}
                className="panel absolute left-1/2 top-6 flex w-[min(90%,22rem)] -translate-x-1/2 flex-col gap-2 p-4 shadow-lg"
              >
                <label htmlFor="field-name" className="text-sm font-medium">
                  Name this field
                </label>
                <input
                  id="field-name"
                  autoFocus
                  required
                  maxLength={80}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="North plot"
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-healthy"
                />
                {error && <p className="text-sm text-stress">{error}</p>}
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="flex-1 rounded-md bg-healthy px-3 py-2 text-sm font-medium text-background disabled:opacity-50"
                  >
                    {saving ? "Saving…" : "Save field"}
                  </button>
                  <button
                    type="button"
                    onClick={cancel}
                    className="rounded-md border border-border px-3 py-2 text-sm text-muted"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
            {!drawing && !pending && fields.length > 0 && (
              <div className="pointer-events-none absolute left-1/2 top-6 -translate-x-1/2">
                <p className="panel px-4 py-2 text-sm text-muted">
                  Select a field to see its health, or draw a new one.
                </p>
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
