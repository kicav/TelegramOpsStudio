# Product specification — consolidated from the supplied videos and reverse-engineered installer

## Final module map

| Observed component | Final implementation |
|---|---|
| Account Creator / User Authorization | Accounts & Sessions: API ID/Hash + phone + OTP + 2FA, persistent Telethon session |
| Multi-account manager | Account registry, explicit account selection per job |
| Session storage | Local Telethon session files; API Hash stored in OS keyring |
| Proxy / DCOM / proxy pool | Proxy Pool + per-account manual assignment; no automatic anti-restriction rotation |
| Get Members by link | Public aggregate overview; detailed member scan only for groups administered by account |
| Get Members from joined group | Same scanner using a joined/managed group identifier |
| Member ID / access hash | SQLite stores `user_id` and `access_hash` when available |
| Excel/CSV storage | Import/export XLSX and CSV |
| Filter bots/deleted/activity | Local filter data model; bot/deleted fields and last-seen category retained |
| Filter one/two file workflows | Import lists into a common member store, then filter/deduplicate there |
| Add by member/group | Invite Queue, explicit target permissions + consent gate |
| Range/limit / remain-success-fail | Per-job limit and structured job/action counters/logs |
| Multi-thread worker | QThreadPool for non-UI background tasks; invite jobs intentionally do not parallelize platform actions |
| Account quota/rotation | Daily/job caps retained in settings; restriction-triggered account rotation deliberately disabled |
| Group messaging | Managed-group message sender |
| User messaging | Opted-in user campaign sender |
| Seeding | Managed-group scripted message sequence with delay and reply-to index |
| Join / leave channel/group | Explicit selected-account Join / Leave |
| Get messages from group | Managed-group message archive with text, sender, reply relationship and media metadata |
| Export to seeding | Archived data is exportable; scripts can be prepared from exported message data |
| Dashboard / logs | SQLite-backed counts and action log viewer |
| Settings | Delay/cap/update settings |
| License | Local license metadata surface; no hard-coded signing secret |
| Updater | HTTPS manifest + SHA-256 verification helper; production should add a digital signature |
| Build / packaging | Nuitka standalone Windows build script; no PDB shipping by default |

## Core data flow

```text
Telegram account
    ↓
Authorized Telethon session
    ↓
Group resolver + permission inspection
    ├─ public group → aggregate overview
    └─ managed group → detailed member/message scan
                          ↓
                       SQLite
                          ↓
                 filter + consent state
                          ↓
                 queue / campaign job
                    ┌─────┴─────┐
                 Invite       Message
                    │             │
           managed target   managed group / opted-in user
                    └─────┬─────┘
                          ↓
                  structured logs
```

## Safety/quality changes from the analyzed binaries

The analyzed products expose features such as account rotation, proxy rotation and bulk stranger outreach that can be used to evade Telegram restrictions. The final product retains the same product modules but changes those mechanisms:

- `FloodWait` stops the job instead of moving to another account.
- Proxy Pool is connectivity configuration, manually assigned per account.
- Detailed identity scraping requires administrator/creator status for the group.
- Invite Queue requires target administrator/invite rights and `opted_in` member state.
- Direct-message campaigns only select `opted_in` members.
- Seeding and group-message scripts run only in groups the selected account administers.

This preserves the engineering value and UI/function coverage while keeping the application suitable for legitimate group administration, community migration and consent-based communication.
