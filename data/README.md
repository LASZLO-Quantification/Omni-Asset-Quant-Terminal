# Runtime Data

The application creates these local files at runtime:

- `trade_history.csv`
- `mapping_templates.json`
- `portfolio_state.json`

They are ignored by Git so a normal research session does not dirty the
repository or publish account-like state. `trade_history.example.csv` is a
synthetic schema example only.

Docker Compose stores `/app/data` in the named `quant-data` volume. Back up or
remove that volume explicitly when you want to preserve or reset local state.
