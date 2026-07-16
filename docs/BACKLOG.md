# Backlog

Deliberately out of scope for v1 (per the approved roadmap's deferred list).
Nothing here should be built without an explicit scope decision.

## Deferred features
- WhatsApp delivery of alerts and advice
- Multi-crop calendars
- NDRE / EVI indices
- Financial impact estimates
- Government scheme matching
- Historical yield correlation
- Mobile app

## Engineering notes raised during the build
- Basemap is Esri World Imagery via the public ArcGIS tile endpoint. Fine for
  development and a demo with attribution, but it is not a licensed production
  basemap. Before any real launch, either sign up for an Esri key or move to a
  self-serve alternative.
- Starlette's `TestClient` emits a deprecation warning asking for `httpx2`.
  Harmless today; revisit if it becomes an error on a future Starlette bump.
