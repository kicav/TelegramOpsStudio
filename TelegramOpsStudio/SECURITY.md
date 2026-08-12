# Security notes

- Never commit `.session` files. A valid user session can grant account access.
- Never commit Telegram API Hash, OTP, 2FA password, proxy passwords, code-signing certificates or private keys.
- API Hash and proxy passwords are stored through the OS credential store.
- Updates require HTTPS and a SHA-256 digest from the update manifest before the downloaded file is accepted.
- Production distribution should additionally Authenticode-sign the final executable and use a signed update manifest.
- The GitHub workflow does not require live Telegram credentials.
