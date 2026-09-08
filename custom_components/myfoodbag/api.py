"""Read-only account client; isolated cookies and automatic OAuth refresh."""
import asyncio
import base64
import hashlib
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlparse

import aiohttp
from .const import API, IDENTITY, TENANT, POLICY, CLIENT_ID, REDIRECT, SCOPE, SUBSCRIPTION_KEY


class AuthError(Exception):
    """Login must be repeated."""


class ApiError(Exception):
    """Account service unavailable or returned unexpected data."""


class Client:
    def __init__(self, session, email, password):
        self.session = session
        self.email = email
        self.password = password
        self.access_token = None
        self.refresh_token = None
        self.expires = 0
        self.lock = asyncio.Lock()

    async def _token(self, data):
        async with self.session.post(
            IDENTITY + TENANT + "/oauth2/v2.0/token",
            params={"p": POLICY},
            data={"client_id": CLIENT_ID, "p": POLICY, **data},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status in (400, 401, 403):
                raise AuthError("Token rejected")
            if response.status != 200:
                raise ApiError("Token service unavailable")
            result = await response.json()
        if not result.get("access_token"):
            raise AuthError("No access token")
        self.access_token = result["access_token"]
        self.refresh_token = result.get("refresh_token", self.refresh_token)
        self.expires = time.monotonic() + int(result.get("expires_in", 3600)) - 120

    async def login(self):
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(32)
        params = dict(p=POLICY, client_id=CLIENT_ID, redirect_uri=REDIRECT,
                      response_type="code", scope=SCOPE, state=state,
                      nonce=secrets.token_urlsafe(32), code_challenge=challenge,
                      code_challenge_method="S256")
        # B2C rejects quoted cookie values. Keep its cookies isolated from HA.
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                   cookie_jar=aiohttp.CookieJar(quote_cookie=False)) as session:
            async with session.get(IDENTITY + TENANT + "/oauth2/v2.0/authorize", params=params) as response:
                if response.status != 200:
                    raise ApiError("Login service unavailable")
                html = await response.text()
            match = re.search(r'var SETTINGS\s*=\s*(\{.*?\});', html, re.S)
            if not match:
                raise AuthError("Unsupported login page")
            settings = json.loads(match[1])
            query = {"tx": settings["transId"], "p": POLICY}
            headers = {"X-CSRF-TOKEN": settings["csrf"], "X-Requested-With": "XMLHttpRequest"}
            base = IDENTITY + TENANT + "/" + POLICY
            async with session.post(base + "/SelfAsserted", params=query, headers=headers,
                                    data={"request_type": "RESPONSE", "email": self.email,
                                          "password": self.password}) as response:
                if response.status >= 500:
                    raise ApiError("Login service unavailable")
                if response.status != 200:
                    raise AuthError("Credentials rejected or interactive login required")
                try:
                    # B2C returns JSON as text/json, which aiohttp rejects by default.
                    result = await response.json(content_type=None)
                except ValueError as err:
                    raise AuthError("Unexpected login page or interactive login required") from err
                if not isinstance(result, dict) or str(result.get("status")) != "200":
                    raise AuthError("Credentials rejected or interactive login required")
            async with session.get(base + "/api/CombinedSigninAndSignup/confirmed",
                                   params={**query, "rememberMe": "true", "csrf_token": settings["csrf"]},
                                   allow_redirects=False) as response:
                location = response.headers.get("Location", "")
            callback = urlparse(location)
            values = parse_qs(callback.query)
            expected = urlparse(REDIRECT)
            if ((callback.scheme, callback.netloc, callback.path.rstrip("/")) !=
                    (expected.scheme, expected.netloc, expected.path.rstrip("/"))
                    or values.get("state") != [state] or not values.get("code")):
                raise AuthError("Login callback invalid or interactive login required")
        await self._token({"grant_type": "authorization_code", "code": values["code"][0],
                           "code_verifier": verifier, "redirect_uri": REDIRECT})

    async def authenticate(self):
        async with self.lock:
            if self.access_token and time.monotonic() < self.expires:
                return
            if self.refresh_token:
                try:
                    await self._token({"grant_type": "refresh_token", "refresh_token": self.refresh_token})
                    return
                except AuthError:
                    self.refresh_token = None
            await self.login()

    async def get(self, path, params=None, optional=False):
        for attempt in range(2):
            await self.authenticate()
            async with self.session.get(API + path, params=params,
                                        headers={"Authorization": "Bearer " + self.access_token,
                                                 "ocp-apim-subscription-key": SUBSCRIPTION_KEY,
                                                 "x-mfb-platform": "ios",
                                                 "x-mfb-app-version": "8.9.0",
                                                 "Accept": "application/json",
                                                 "User-Agent": "MyFoodBag/211 CFNetwork/3860.700.1 Darwin/25.6.0"},
                                        timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 401:
                    self.expires = 0
                    if attempt == 0:
                        continue
                    raise AuthError("Account authorization expired")
                if response.status == 403:
                    raise AuthError("Account access denied")
                if optional and response.status in (204, 404):
                    return None
                if response.status != 200:
                    raise ApiError(f"Account service returned HTTP {response.status}")
                try:
                    return await response.json()
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise ApiError("Invalid account response") from err
