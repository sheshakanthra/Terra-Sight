import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set in apps/web/.env.local",
  );
}

/**
 * Browser-side Supabase client.
 *
 * The session lives in the browser and its access token is forwarded to the
 * API as a bearer token, where PostgREST applies row-level security. The
 * anon key is public by design; the service-role key must never appear here.
 */
export const supabase = createClient(url, anonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
