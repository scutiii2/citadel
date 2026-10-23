import base64
import json

import httpx
import pytest


def test_package_routes_require_access_and_proxy_fixed_paths(client, db_gateway, upstream):
    assert client.post('/api/video-downloader/packages', json={'name': 'Mix'}).status_code == 401
    enable(client, db_gateway, 'video')
    upstream.handler = lambda r: httpx.Response(200, json={'package_id': 'p_one', 'job_id': 'j_one'})
    cases = [
        ('POST', '/packages', {'name': 'Mix'}),
        ('GET', '/packages', None),
        ('GET', '/packages/p_one', None),
        ('POST', '/packages/p_one/items', {'url': 'https://example.com/a', 'preset': 'best'}),
        ('DELETE', '/packages/p_one/items/i_one', None),
        ('POST', '/packages/p_one/start', {}),
    ]
    for method, path, body in cases:
        assert client.request(method, '/api/video-downloader' + path, json=body).status_code == 200
        assert upstream.requests[-1].url.path == '/video/ui' + path
    upstream.handler = lambda r: httpx.Response(409, json={'error': {'code': 'package_locked', 'message': 'Locked'}})
    response = client.post('/api/video-downloader/packages/p_one/items', json={'url': 'https://example.com/b'})
    assert response.status_code == 409 and response.json()['error']['code'] == 'package_locked'


def test_package_delete_requires_login_and_proxies_conflicts(client, upstream):
    path = '/api/video-downloader/packages/p_one'
    assert client.delete(path).status_code == 401
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(409, json={'error': {'code': 'package_locked', 'message': 'Still downloading'}})
    assert client.delete(path).status_code == 409
    upstream.handler = lambda r: httpx.Response(200, json={'ok': True})
    assert client.delete(path).status_code == 204
    assert upstream.requests[-1].method == 'DELETE'
    assert upstream.requests[-1].url.path == '/video/ui/packages/p_one'

from tests.test_registration import as_admin
from tests.test_permission_split import limited_account


def enable(client, db_gateway, *areas):
    as_admin(client)
    from sqlalchemy import select
    from src.models import Account
    from tests.conftest import ADMIN_USERNAME
    async def account_uid():
        async with client.app.state.database.sessions() as session:
            return await session.scalar(select(Account.uid).where(Account.username == ADMIN_USERNAME))
    uid = client.portal.call(account_uid)
    db_gateway.records[('account_capabilities', uid)] = {'capabilities': list(areas)}
    return uid


@pytest.mark.parametrize('area', ['pdf-merger', 'video-downloader'])
def test_login_is_required(client, area, upstream):
    assert client.get(f'/api/{area}/files').status_code == 401
    assert not upstream.requests


@pytest.mark.parametrize('area', ['pdf-merger', 'video-downloader'])
def test_tools_view_cannot_execute(client, email, area):
    limited_account(client, email, 'tools.view')
    assert client.get(f'/api/{area}/files').status_code == 403


def test_files_and_jobs_use_trusted_identity_and_local_download_links(client_factory, db_gateway, upstream):
    client = client_factory(internal_token='test-internal')
    uid = enable(client, db_gateway, 'pdf', 'video')
    def serve(request):
        area = request.url.path.split('/')[1]
        file = {'file_id': 'f_one', 'download_url': f'http://private/{area}/files/f_one/download?exp=42&sig=secret'}
        return httpx.Response(200, json=[file] if request.url.path.endswith('/files') else {'result': file})
    upstream.handler = serve
    for area, public in [('pdf', 'pdf-merger'), ('video', 'video-downloader')]:
        result = client.get(f'/api/{public}/files', headers={'X-Requester-Uid': 'other', 'X-Internal-Token': 'evil'})
        assert result.status_code == 200, result.text
        assert result.json()[0]['download_url'] == f'/api/{public}/files/f_one/download'
        request = upstream.requests[-1]
        assert request.url.path == f'/{area}/ui/files'
        assert request.headers['x-requester-uid'] == uid
        assert request.headers['x-internal-token'] == 'test-internal'
        job = client.get(f'/api/{public}/jobs/j_one')
        assert job.json()['result']['download_url'] == f'/api/{public}/files/f_one/download'


def test_upload_is_json_bounded_and_returns_original_metadata(client, db_gateway, upstream):
    enable(client, db_gateway, 'pdf')
    metadata = {'file_id': 'f_one', 'name': 'scan.pdf', 'kind': 'pdf', 'pages': 2, 'size': 9, 'expires_at': 2000000000}
    upstream.handler = lambda r: httpx.Response(200, json=metadata)
    response = client.post('/api/pdf-merger/files', json={'filename': 'C:\\docs\\scan.pdf', 'data': base64.b64encode(b'%PDF-test').decode()})
    assert response.status_code == 200, response.text
    assert response.json() == metadata
    assert upstream.requests[-1].url.path == '/upload/pdf'
    assert b'filename="scan.pdf"' in upstream.requests[-1].content
    assert client.post('/api/pdf-merger/files', json={'filename': 'x.pdf', 'data': '???'}).status_code == 400
    assert client.post('/api/pdf-merger/files', json={'filename': 'x.exe', 'data': 'eA=='}).status_code == 400
    assert client.post('/api/pdf-merger/files', content=b'raw', headers={'Content-Type': 'application/octet-stream'}).status_code == 415
    assert client.post('/api/pdf-merger/files', json={'filename': 'x.pdf', 'data': 'A' * (20 * 1024 * 1024 + 4)}).status_code == 422


def test_merge_probe_start_cancel_and_delete_use_fixed_paths(client, db_gateway, upstream):
    enable(client, db_gateway, 'pdf', 'video')
    upstream.handler = lambda r: httpx.Response(200, json={'job_id': 'j_one', 'ok': True})
    plan = {'segments': [{'file_id': 'f_one', 'pages': '2,1'}, {'file_id': 'f_two', 'pages': 'all', 'rotate': 90}]}
    assert client.post('/api/pdf-merger/merge', json=plan).status_code == 200
    assert upstream.requests[-1].url.path == '/pdf/ui/merge'
    assert json.loads(upstream.requests[-1].content)['segments'][0]['pages'] == '2,1'
    assert client.post('/api/pdf-merger/merge', json={'segments': []}).status_code == 422
    assert client.post('/api/video-downloader/probe', json={'url': 'http://localhost/private'}).status_code == 200
    assert upstream.requests[-1].url.path == '/video/ui/probe'  # Armory, not this proxy, owns UrlPolicy.
    assert client.post('/api/video-downloader/downloads', json={'url': 'https://public.example/v', 'preset': 'best'}).status_code == 200
    for public, area in [('pdf-merger', 'pdf'), ('video-downloader', 'video')]:
        assert client.post(f'/api/{public}/jobs/j_one/cancel', json={}).status_code == 200
        assert upstream.requests[-1].url.path == f'/{area}/ui/jobs/j_one/cancel'
        assert client.delete(f'/api/{public}/files/f_one').status_code == 204


def test_policy_errors_missing_files_and_unavailable_upstream(client, db_gateway, upstream):
    enable(client, db_gateway, 'video')
    upstream.handler = lambda r: httpx.Response(400, json={'error': {'code': 'url_blocked', 'message': 'Use a public URL.'}})
    response = client.post('/api/video-downloader/probe', json={'url': 'http://127.0.0.1'})
    assert response.status_code == 400 and response.json()['error']['code'] == 'url_blocked'
    upstream.handler = lambda r: httpx.Response(404, json={'error': {'code': 'file_not_found', 'message': 'Unavailable'}})
    assert client.delete('/api/video-downloader/files/f_foreign').status_code == 404
    upstream.unreachable = True
    assert client.get('/api/video-downloader/files').status_code == 502


def test_download_checks_ownership_and_never_follows_foreign_origins(client, db_gateway, upstream):
    enable(client, db_gateway, 'video')
    def serve(request):
        if request.url.path == '/video/ui/files':
            return httpx.Response(200, json=[{'file_id': 'f_one', 'download_url': 'http://untrusted.invalid/video/files/f_one/download?exp=42&sig=test'}])
        assert request.url.host == 'mcp-server.internal'
        return httpx.Response(206, content=b'clip', headers={'content-type': 'video/mp4', 'content-range': 'bytes 0-3/4'})
    upstream.handler = serve
    assert client.get('/api/video-downloader/files/f_other/download').status_code == 404
    response = client.get('/api/video-downloader/files/f_one/download', headers={'Range': 'bytes=0-3'})
    assert response.status_code == 206 and response.content == b'clip'
    assert response.headers['cache-control'] == 'no-store'
    assert upstream.requests[-1].headers['range'] == 'bytes=0-3'


def test_download_accepts_public_proxy_prefix_but_fetches_fixed_internal_path(client, db_gateway, upstream):
    enable(client, db_gateway, 'video')
    def serve(request):
        if request.url.path == '/video/ui/files':
            return httpx.Response(200, json=[{'file_id': 'f_one', 'download_url':
                'https://public.example/armory/video/files/f_one/download?exp=42&sig=test'}])
        assert request.url.host == 'mcp-server.internal'
        assert request.url.path == '/video/files/f_one/download'
        assert request.url.query == b'exp=42&sig=test'
        return httpx.Response(200, content=b'clip')
    upstream.handler = serve
    response = client.get('/api/video-downloader/files/f_one/download')
    assert response.status_code == 200 and response.content == b'clip'


def test_pdf_content_remains_account_scoped(client, db_gateway, upstream):
    uid = enable(client, db_gateway, 'pdf')
    def serve(request):
        assert request.url.path == '/pdf/ui/files/f_one/content'
        assert request.headers['x-requester-uid'] == uid
        return httpx.Response(200, content=b'%PDF-test', headers={'content-type': 'application/pdf'})
    upstream.handler = serve
    response = client.get('/api/pdf-merger/files/f_one/content')
    assert response.status_code == 200 and response.content == b'%PDF-test'
    assert response.headers['content-security-policy'] == 'sandbox'


@pytest.mark.parametrize('status,code,message', [
    (403, 'blocked_host', 'Only public hosts are supported.'),
    (503, 'ffmpeg_missing', 'Install FFmpeg on Armory.'),
])
def test_actionable_policy_and_dependency_errors_survive_proxy(client, db_gateway, upstream, status, code, message):
    enable(client, db_gateway, 'video')
    upstream.handler = lambda r: httpx.Response(status, json={'error': {'code': code, 'message': message}})
    response = client.post('/api/video-downloader/probe', json={'url': 'http://127.0.0.1'})
    assert response.status_code == status
    assert response.json()['error'] == {'code': code, 'message': message}


@pytest.mark.parametrize('status', [401, 403, 500, 503, 302])
def test_connection_failures_hide_internal_details(client, db_gateway, upstream, status):
    enable(client, db_gateway, 'pdf')
    upstream.handler = lambda r: httpx.Response(status, json={'error': 'private internals'})
    response = client.get('/api/pdf-merger/files')
    assert response.status_code == 502
    assert 'private' not in response.text


@pytest.mark.parametrize('link', [
    'http://other.invalid/private?exp=1&sig=x',
    'http://other.invalid/video/files/f_one/download',
    'http://[invalid/video/files/f_one/download?exp=1&sig=x',
])
def test_download_rejects_invalid_signed_path(client, db_gateway, upstream, link):
    enable(client, db_gateway, 'video')
    upstream.handler = lambda r: httpx.Response(200, json=[{'file_id': 'f_one', 'download_url': link}])
    count = len(upstream.requests)
    response = client.get('/api/video-downloader/files/f_one/download')
    assert response.status_code == 502
    assert len(upstream.requests) == count + 1


def test_content_decodes_compression_without_forwarding_wrong_length(client, db_gateway, upstream):
    import gzip
    enable(client, db_gateway, 'pdf')
    compressed = gzip.compress(b'%PDF-test')
    upstream.handler = lambda r: httpx.Response(200, content=compressed, headers={
        'content-type': 'application/pdf', 'content-encoding': 'gzip', 'content-length': str(len(compressed)),
    })
    response = client.get('/api/pdf-merger/files/f_one/content')
    assert response.content == b'%PDF-test'
    assert 'content-length' not in response.headers
    assert upstream.requests[-1].headers['accept-encoding'] == 'identity'


@pytest.mark.parametrize('status', [201, 204])
def test_content_rejects_unexpected_success_status(client, db_gateway, upstream, status):
    enable(client, db_gateway, 'pdf')
    upstream.handler = lambda r: httpx.Response(status)
    assert client.get('/api/pdf-merger/files/f_one/content').status_code == 502


def test_transfer_permissions_are_independent_of_tool_execution(client, email, db_gateway, upstream):
    from src.models import Account
    from sqlalchemy import select
    limited_account(client, email, 'tools.execute')
    async def member_uid():
        async with client.app.state.database.sessions() as session:
            return await session.scalar(select(Account.uid).where(Account.username == 'alice'))
    uid = client.portal.call(member_uid)
    db_gateway.records[('account_capabilities', uid)] = {'capabilities': ['pdf', 'video']}
    assert client.post('/api/pdf-merger/files', json={'filename': 'x.pdf', 'data': 'eA=='}).status_code == 403
    assert client.get('/api/pdf-merger/files/f_one/content').status_code == 403
    assert client.get('/api/video-downloader/files/f_one/download').status_code == 403
    assert not upstream.requests
