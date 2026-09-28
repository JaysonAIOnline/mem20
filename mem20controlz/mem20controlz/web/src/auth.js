// Session handling for the control plane.
//
// Two independent things can admit a request: a Cloudflare Access identity
// header (when the control plane is behind Access) or the admin session cookie
// issued after a password login. This module only asks which one applies and
// drives the login form; it never stores the password.

import { getJSON, postJSON } from "./api.js";

export function fetchAuthStatus() {
  return getJSON("/api/auth/status");
}

export async function login(password) {
  return postJSON("/api/auth/login", { password });
}

export async function logout() {
  return postJSON("/api/auth/logout", {});
}

export function isUnauthorized(err) {
  return Boolean(err) && err.status === 401;
}
