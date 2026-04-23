#!/usr/bin/env python3
"""Generate GitHub App installation token.

Used by GitHub Actions workflow to authenticate as the echo-agent GitHub App.
Reads APP_ID, INSTALL_ID, APP_PRIVATE_KEY from environment variables.
Outputs the token to GITHUB_OUTPUT.
"""

import jwt, time, json, urllib.request, os

pem = os.environ['APP_PRIVATE_KEY']
app_id = os.environ['APP_ID']
install_id = os.environ['INSTALL_ID']

now = int(time.time())
jwt_token = jwt.encode(
    {'iat': now - 60, 'exp': now + 600, 'iss': app_id},
    pem,
    algorithm='RS256'
)

req = urllib.request.Request(
    f'https://api.github.com/app/installations/{install_id}/access_tokens',
    method='POST',
    headers={
        'Authorization': f'Bearer {jwt_token}',
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
    },
    data=b'{}',
)

with urllib.request.urlopen(req, timeout=30) as resp:
    token = json.loads(resp.read())['token']

with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
    f.write(f'token={token}')

print(f'Generated installation token for app {app_id}')
