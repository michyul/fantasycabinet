# Authentik integration notes

## Integration mode

- OIDC Authorization Code flow for web login.
- JWT access token validated by API against Authentik JWKS.

## Required claims

- `sub` (stable external user ID)
- `email`
- `name` or preferred username
- optional role/group claims for commissioner/admin bootstrap

## Required configuration

- Provider issuer URL in `.env` (`OIDC_ISSUER`)
- Client ID and secret
- Callback URL: `/api/auth/callback` on web domain
- Logout redirect URLs

## Recommended hardening

- Short-lived access tokens + refresh token rotation
- Strict allowed redirect URIs
- Enforce PKCE for public client patterns
