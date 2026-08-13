# Security

## Never commit

- `*.session` / `*.session-journal`
- API hashes or 2FA/OTP values
- `.env` files
- runtime SQLite databases
- exports containing identifiers
- proxy passwords
- PDB/debug symbols

The repository `.gitignore` blocks these classes of files.

## Session handling

A Telethon session is credential-like and must be treated as a reusable login credential. Runtime sessions live under the local application-data directory and never in `Program Files` or the repository.

## Secret storage

`SecretStore` is an abstraction. The Windows-oriented production implementation uses the OS credential backend through `keyring`; the database stores only a secret reference.

## Logging

Application/operation/audit data must not contain:

- session authorization material
- API hash
- OTP
- 2FA password
- raw access credentials

Business errors are normalized before display. Raw tracebacks belong to diagnostics only.

## Telegram policy boundary

- No participant-list bypass.
- No fallback scraping of recent message senders when the member list is unavailable.
- No FloodWait evasion.
- No account/proxy rotation for the purpose of continuing after restrictions.
- No live bulk messaging implementation in this repository.
- Live membership side effects are not implemented in `TelethonReadOnlyAdapter`.
