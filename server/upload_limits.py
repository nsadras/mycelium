"""Bound audio request bytes before Starlette can spool multipart files."""
from collections.abc import Callable

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse


class AudioUploadLimitMiddleware:
    def __init__(self, app, max_body_bytes: Callable[[], int]):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] != '/api/engram/meetings/upload':
            return await self.app(scope, receive, send)
        limit = self.max_body_bytes()
        lengths = [value for name, value in scope.get('headers', []) if name.lower() == b'content-length']
        try:
            if len(lengths) > 1 or (lengths and int(lengths[0]) < 0):
                raise ValueError('Invalid content length')
            declared = int(lengths[0]) if lengths else None
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length'}, status_code=400)(scope, receive, send)
        rejected = JSONResponse({'detail': 'Audio request exceeds the configured size limit'}, status_code=413)
        if declared is not None and declared > limit:
            return await rejected(scope, receive, send)
        received = 0
        exceeded = False

        async def bounded_receive():
            nonlocal received, exceeded
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > limit:
                    exceeded = True
                    # Starlette closes partial spooled files for this exception.
                    raise MultiPartException('Audio request exceeds size limit')
            return message

        async def bounded_send(message):
            if not exceeded:
                await send(message)

        try:
            await self.app(scope, bounded_receive, bounded_send)
        except MultiPartException:
            if not exceeded:
                raise
        if exceeded:
            await rejected(scope, receive, send)
