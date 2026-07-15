export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6 py-16">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">TerraSight</h1>
        <p className="mt-3 text-balance text-muted">
          Satellite-derived field health and plain-language advice for
          smallholder farms.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-5">
        <p className="text-sm text-muted">
          Draw a field, and TerraSight reads recent Sentinel-2 passes through
          the cloud gaps, tracks NDVI across a 3×3 zone grid, and explains what
          changed — with the numbers behind every recommendation.
        </p>
      </div>

      <p className="font-mono text-xs text-muted">Phase 0 — scaffold</p>
    </main>
  );
}
