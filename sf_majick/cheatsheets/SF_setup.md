# Salesforce Simulation Cheatsheet

This cheatsheet summarizes key steps and commands for running your Salesforce simulation project in Python.

---

## 1️⃣ Environment Variables

Store credentials securely in a `.env` file (hidden from GitHub via `.gitignore`):

```
SF_CLIENT_ID=your_client_id_here
SF_CLIENT_SECRET=your_client_secret_here
SF_REFRESH_TOKEN=your_refresh_token_here
SF_INSTANCE_URL=https://<your-domain>.my.salesforce.com
```

> **Tip:** Do NOT wrap values in quotes. Keep `.env` in your project root and add to `.gitignore`.

---

## 2️⃣ Loading Environment Variables

```python
from dotenv import load_dotenv
import os

load_dotenv("/full/path/to/.env")

CLIENT_ID = os.environ.get("SF_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SF_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("SF_REFRESH_TOKEN")
INSTANCE_URL = os.environ.get("SF_INSTANCE_URL")
```

---

## 3️⃣ PKCE Authorization Flow (Manual or Localhost)

### Step 1: Generate Code Challenge

```python
import secrets, hashlib, base64

code_verifier = secrets.token_urlsafe(64)
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode("utf-8")
```

### Step 2: Build Authorization URL

```python
from urllib.parse import urlencode

REDIRECT_URI = "http://localhost:8080/callback"

auth_params = {
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "code_challenge": code_challenge,
    "code_challenge_method": "S256"
}

auth_url = f"https://login.salesforce.com/services/oauth2/authorize?{urlencode(auth_params)}"
print("Open in browser:", auth_url)
```

### Step 3: Capture `code`

* If using manual redirect: copy `code` parameter from URL.
* If using localhost server:

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.code = parse_qs(urlparse(self.path).query).get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"You can close this tab now!")

httpd = HTTPServer(('localhost', 8080), Handler)
httpd.handle_request()
auth_code = httpd.code
```

### Step 4: Exchange for Access + Refresh Token

```python
import requests

token_url = "https://login.salesforce.com/services/oauth2/token"
payload = {
    "grant_type": "authorization_code",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
    "code": auth_code,
    "code_verifier": code_verifier
}

r = requests.post(token_url, data=payload)
r.raise_for_status()
tokens = r.json()

print("Access Token:", tokens.get("access_token"))
print("Refresh Token:", tokens.get("refresh_token"))
print("Instance URL:", tokens.get("instance_url"))
```

---

## 4️⃣ Save Tokens to `.env`

```python
with open(".env", "a") as f:
    f.write(f"SF_REFRESH_TOKEN={tokens.get('refresh_token')}\n")
    f.write(f"SF_INSTANCE_URL={tokens.get('instance_url')}\n")
```

---

## 5️⃣ Running Simulation

```bash
python build_baseline.py
python run_simulation.py --days=300 --runs=20
```

---

## 6️⃣ Recommended Git Setup

```bash
echo ".env" >> .gitignore
git add .gitignore
```

Keep credentials local and never push `.env` to GitHub.

---

## 7️⃣ References

* Salesforce OAuth2 PKCE Flow: [https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/intro_understanding_oauth_pkce.htm](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/intro_understanding_oauth_pkce.htm)
* Python `requests`: [https://docs.python-requests.org](https://docs.python-requests.org)
* Python `dotenv`: [https://pypi.org/project/python-dotenv/](https://pypi.org/project/python-dotenv/)
