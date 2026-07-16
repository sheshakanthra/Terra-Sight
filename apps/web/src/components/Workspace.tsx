"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { ApiError, createField, listFields } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import type { Field, PolygonGeometry } from "@/lib/types";

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
  const [drawing, setDrawing] = useState(false);
  const [pending, setPending] = useState<PolygonGeometry | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
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
    void refresh();
  }, [refresh]);

  const handlePolygonDrawn = useCallback((geometry: PolygonGeometry) => {
    setPending(geometry);
    setDrawing(false);
    setError(null);
  }, []);

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
    } catch (err) {
      // A rejected polygon (too small, self-intersecting) keeps its shape on
      // screen so the message makes sense against what was actually drawn.
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

  return (
    <main className="flex h-screen flex-col md:flex-row">
      <aside className="flex w-full shrink-0 flex-col gap-4 border-border p-5 md:w-80 md:border-r">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold tracking-tight">TerraSight</h1>
          <button
            onClick={() => void supabase.auth.signOut()}
            className="text-xs text-muted underline-offset-2 hover:underline"
          >
            Sign out
          </button>
        </div>
        <p className="truncate text-xs text-muted">{session.user.email}</p>

        {pending ? (
          <form onSubmit={save} className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
            <label htmlFor="field-name" className="text-sm font-medium">
              Name this field
            </label>
            <input
              id="field-name"
              autoFocus
              required
              maxLength={80}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="North plot"
              className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-healthy"
            />
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
        ) : (
          <button
            onClick={() => setDrawing((on) => !on)}
            className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              drawing
                ? "border border-healthy text-healthy"
                : "bg-healthy text-background hover:opacity-90"
            }`}
          >
            {drawing ? "Cancel drawing" : "Draw a field"}
          </button>
        )}

        {drawing && (
          <p className="text-xs text-muted">
            Click each corner of your field. Click the first corner again to finish.
          </p>
        )}

        {error && (
          <p className="rounded-md border border-stress/40 bg-stress/10 px-3 py-2 text-sm text-stress">
            {error}
          </p>
        )}

        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
          <h2 className="text-xs font-medium uppercase tracking-wide text-muted">
            Your fields {fields.length > 0 && `(${fields.length})`}
          </h2>
          {loading ? (
            <p className="text-sm text-muted">Loading…</p>
          ) : fields.length === 0 ? (
            <p className="text-sm text-muted">
              No fields yet. Draw your first one on the map.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {fields.map((field) => (
                <li
                  key={field.id}
                  className="rounded-md border border-border bg-surface px-3 py-2"
                >
                  <p className="truncate text-sm font-medium">{field.name}</p>
                  <p className="font-mono text-xs text-muted">
                    {field.area_ha.toFixed(2)} ha
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <div className="min-h-0 flex-1">
        <FieldMap fields={fields} drawing={drawing} onPolygonDrawn={handlePolygonDrawn} />
      </div>
    </main>
  );
}
