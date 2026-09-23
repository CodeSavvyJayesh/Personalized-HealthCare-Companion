/**
 * API base URL.
 *
 * Hardcoding 127.0.0.1 meant the built bundle only ever worked on the
 * machine that ran the API. This reads REACT_APP_API_URL at build time so
 * the same code deploys anywhere (see frontend/.env.example).
 */
const API_URL = (
  process.env.REACT_APP_API_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export default API_URL;
