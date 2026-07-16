"use client";

import { useState } from "react";
import { supabase } from "@/lib/supabase";

export default function SignIn() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  async function sendMagicLink(event: React.FormEvent) {
    event.preventDefault();
    setStatus("sending");
    setError(null);

    const { error: signInError } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });

    if (signInError) {
      setError(signInError.message);
      setStatus("idle");
      return;
    }
    setStatus("sent");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">TerraSight</h1>
        <p className="mt-2 text-sm text-muted">
          Satellite-derived field health for smallholder farms.
        </p>
      </div>

      {status === "sent" ? (
        <div className="rounded-lg border border-border bg-surface p-5">
          <p className="text-sm">
            Check <span className="font-medium">{email}</span> for a sign-in link.
          </p>
          <p className="mt-2 text-sm text-muted">
            You can close this tab — the link opens TerraSight directly.
          </p>
        </div>
      ) : (
        <form onSubmit={sendMagicLink} className="flex flex-col gap-3">
          <label htmlFor="email" className="text-sm text-muted">
            Sign in with your email — no password needed.
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-healthy"
          />
          <button
            type="submit"
            disabled={status === "sending"}
            className="rounded-md bg-healthy px-3 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {status === "sending" ? "Sending…" : "Send sign-in link"}
          </button>
          {error && <p className="text-sm text-stress">{error}</p>}
        </form>
      )}
    </main>
  );
}
