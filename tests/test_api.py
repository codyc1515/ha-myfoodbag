import time
import pytest
from mfb.api import Client, AuthError, ApiError

class Response:
    def __init__(self, status, data):
        self.status=status
        self.data=data
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def json(self, **kwargs): return self.data

class Session:
    def __init__(self,*responses): self.responses=list(responses);self.calls=[]
    def get(self,*args,**kwargs):
        self.calls.append((args,kwargs));return self.responses.pop(0)
    post=get

@pytest.mark.asyncio
async def test_refresh_token_rotation():
    s=Session(Response(200,{'access_token':'new','refresh_token':'rotated','expires_in':3600}))
    c=Client(s,'test@example.invalid','dummy');c.refresh_token='old'
    await c.authenticate()
    assert c.refresh_token == 'rotated' and c.access_token == 'new'
    assert s.calls[0][1]['data']['grant_type']=='refresh_token'

@pytest.mark.asyncio
async def test_unauthorized_retries_once():
    s=Session(Response(401,{}),Response(401,{}));c=Client(s,'','')
    async def auth(): c.access_token='dummy'
    c.authenticate=auth
    with pytest.raises(AuthError): await c.get('/subscriptions/orders')
    assert len(s.calls)==2

@pytest.mark.asyncio
async def test_optional_404():
    c=Client(Session(Response(404,{})),'','');c.access_token='dummy';c.expires=time.monotonic()+999
    assert await c.get('/delivery/tracking/1',optional=True) is None

@pytest.mark.asyncio
async def test_rate_limit_not_swallowed():
    c=Client(Session(Response(429,{})),'','');c.access_token='dummy';c.expires=time.monotonic()+999
    with pytest.raises(ApiError): await c.get('/x',optional=True)

@pytest.mark.asyncio
async def test_expired_refresh_falls_back_to_login():
    c=Client(Session(Response(400,{})),'','');c.refresh_token='expired'
    calls=[]
    async def login(): calls.append(True)
    c.login=login
    await c.authenticate()
    assert calls == [True]

@pytest.mark.asyncio
@pytest.mark.parametrize("callback_suffix,valid", [("", True), ("/", True), ("/unexpected", False)])
async def test_login_pkce_and_csrf(monkeypatch, callback_suffix, valid):
    import json
    from urllib.parse import urlencode
    from mfb import api
    from mfb.const import REDIRECT
    class LoginResponse(Response):
        def __init__(self, status, data=None, html='', headers=None):
            super().__init__(status,data);self.html=html;self.headers=headers or {}
        async def text(self): return self.html
        async def json(self, **kwargs):
            assert kwargs.get('content_type', 'default') is None
            return self.data
    class LoginSession:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def get(self,url,**kwargs):
            if url.endswith('/authorize'):
                self.state=kwargs['params']['state']
                self.challenge=kwargs['params']['code_challenge']
                return LoginResponse(200,html='var SETTINGS = '+json.dumps({'csrf':'csrf-test','transId':'transaction-test'})+';')
            assert kwargs['allow_redirects'] is False
            assert kwargs['params']['csrf_token']=='csrf-test'
            return LoginResponse(302,headers={'Location':REDIRECT+callback_suffix+'?'+urlencode({'state':self.state,'code':'test-code'})})
        def post(self,url,**kwargs):
            assert kwargs['headers']['X-CSRF-TOKEN']=='csrf-test'
            assert kwargs['data']['email']=='test@example.invalid'
            return LoginResponse(200,{'status':'200'})
    login=LoginSession()
    def session_factory(**kwargs):
        from yarl import URL
        jar = kwargs['cookie_jar']
        jar.update_cookies({'b2c': 'value,with,commas'})
        assert jar.filter_cookies(URL('https://example.invalid'))['b2c'].coded_value == 'value,with,commas'
        return login
    monkeypatch.setattr(api.aiohttp,'ClientSession',session_factory)
    s=Session(Response(200,{'access_token':'new','refresh_token':'refresh'}))
    c=Client(s,'test@example.invalid','dummy')
    if not valid:
        with pytest.raises(AuthError):
            await c.login()
        assert not s.calls
        return
    await c.login()
    body=s.calls[0][1]['data']
    import hashlib,base64
    assert base64.urlsafe_b64encode(hashlib.sha256(body['code_verifier'].encode()).digest()).rstrip(b'=').decode()==login.challenge
    assert c.access_token=='new'


@pytest.mark.asyncio
async def test_api_compatibility_headers():
    s = Session(Response(200, {}))
    c = Client(s, '', '')
    c.access_token = 'dummy'
    c.expires = time.monotonic() + 999
    await c.get('/customer/profile/me')
    headers = s.calls[0][1]['headers']
    assert headers['x-mfb-app-version'] == '8.9.0'
    assert headers['User-Agent'].startswith('MyFoodBag/')
    from mfb.const import SUBSCRIPTION_KEY
    assert headers['ocp-apim-subscription-key'] == SUBSCRIPTION_KEY
