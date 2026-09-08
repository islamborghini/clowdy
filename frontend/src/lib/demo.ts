/**
 * Read-only demo mode.
 *
 * Set at build time with VITE_DEMO_MODE, because Vite inlines env vars into
 * the bundle and there is no runtime config to fetch.
 *
 * This flag is cosmetic. It hides controls that would fail so visitors do not
 * click into a wall of 403s -- it is not the security boundary. The backend
 * blocks every write independently in app/middleware/demo_mode.py, and that is
 * the thing actually protecting the host. If the two ever disagree, the worst
 * case is a visible button that returns an error, not an unguarded write.
 */
export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true"
