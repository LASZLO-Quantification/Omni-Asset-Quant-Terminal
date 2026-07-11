# Open-Source Boundary

## Safe to Publish

Public reference repositories can include:

- Generic UI components and workflow navigation.
- Explicit event, signal, execution-estimate, and ledger schemas.
- Deterministic strategy examples using synthetic inputs.
- Constraint and risk-gate examples without production thresholds.
- Local state replay, import/export, and report generation.
- Synthetic datasets, fixtures, tests, CI, and container scaffolding.
- Architecture decisions and failure-mode documentation.

## Keep Private

Do not copy these from a live or paper-trading system into a public reference:

- Wallet keys, seed phrases, API tokens, RPC URLs, or account identifiers.
- Real trade ledgers, positions, incident logs, or operator telemetry.
- Dashcam/feature captures that can reveal proprietary data or behavior.
- Trained model weights, private labels, feature-selection manifests, or alpha thresholds.
- Provider-routing logic, quota policy, and production failover inventories.
- Live execution routing, signing, nonce policy, and anti-abuse controls.
- Internal runbooks that expose infrastructure or recovery credentials.

## Release Checklist

Before publishing a commit or extracting a module:

1. Search the full Git history and working tree for secrets.
2. Replace all runtime data with synthetic fixtures.
3. Confirm `.env`, ledger, state, logs, models, and backups are ignored.
4. Remove production endpoints, account IDs, addresses, and thresholds.
5. Document what is simulated and what is not implemented.
6. Run tests from a clean clone and verify Docker persistence behavior.
7. Review the final diff as if the repository were immediately indexed.

The private LASZLO engine and this public terminal may share engineering
principles, but they should not share production data or execution internals.
