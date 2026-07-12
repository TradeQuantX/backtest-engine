# Authentication Module

## Location
`src/backtest_engine/data_provider/auth/`

## Components
- `token_store.py` - `TokenStore` (encrypted file storage using `cryptography.fernet`)
- `auth_manager.py` - `AuthManager` (coordinates auth for all providers)
- `zerodha_auth.py` - `ZerodhaAuthProvider` (OAuth flow with local HTTP server)
- `dhan_auth.py` - `DhanAuthProvider` (JWT validation)

## TokenStore
- Encrypts tokens with Fernet (AES-128)
- Key derived from machine-specific salt + user password (or env var `TRADEX_ENCRYPTION_KEY`)
- Stores: `access_token`, `refresh_token`, `expires_at`, `provider_metadata`
- Path: `~/.tradex/tokens/{provider}.enc`

## ZerodhaAuthProvider
```python
auth = ZerodhaAuthProvider(config)
await auth.authenticate()  # Opens browser, runs local server on :8080
token = await auth.get_valid_token()  # Returns access_token, refreshes if needed
await auth.refresh_token()  # Uses refresh_token to get new access_token
```

### OAuth Flow
1. Generate login URL: `https://kite.zerodha.com/connect/login?v=3&api_key={api_key}&redirect_url={redirect_url}`
2. Open browser (or print URL for headless)
3. Start HTTP server on `redirect_url` (default `http://127.0.0.1:8080`)
4. User logs in → redirects with `request_token`
5. Exchange: `POST /session/token` with `api_key`, `request_token`, `checksum=sha256(api_key+request_token+api_secret)`
6. Receive `access_token`, `refresh_token`, `user_id`
7. Store encrypted

## DhanAuthProvider
```python
auth = DhanAuthProvider(config)
await auth.authenticate()  # Validates JWT from config
token = await auth.get_valid_token()  # Returns JWT if not expired
```

### JWT Validation
- Decodes without verification (trusts Dhan's 24hr expiry)
- Checks `exp` claim > now + 5min buffer
- Returns token or raises `TokenExpiredError`

## AuthManager
```python
manager = AuthManager(config)
await manager.initialize()  # Authenticates all configured providers
token = await manager.get_token("zerodha")
await manager.refresh_all()  # Refreshes all expired tokens
```