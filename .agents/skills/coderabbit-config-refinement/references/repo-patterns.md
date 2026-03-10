# Repo-Specific Pattern Notes

Use these as defaults, then tune from actual review-loop results.

## React Native / Expo

- High-signal focus areas:
  - auth/session correctness
  - secure storage and sensitive logging
  - navigation/deep-link safety
  - error handling for user-critical flows
- Prefer path instructions by app layer (`features`, `services`, `navigation`, `store`, `hooks`, `components`, `utils`).
- Keep AST rules very narrow; avoid keyword-heavy logging/privacy rules unless proven useful.

## Elixir / Phoenix

- High-signal focus areas:
  - authz/authn in controllers/channels/sockets
  - dangerous execution APIs (eval/OS command)
  - raw SQL interpolation and query safety
  - migration safety and rollback/lock risk
- Prefer separate path instructions for:
  - domain (`lib/<app>/**`)
  - controllers/plugs/router (`lib/<app>_web/...`)
  - channels/socket (`lib/<app>_web/channels/**`)
  - migrations (`priv/repo/migrations`)

> Note: these are illustrative examples — replace with your project's actual paths

- AST rules are useful when limited to deterministic security/correctness sinks.
