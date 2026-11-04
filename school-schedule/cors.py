"""WSGI CORS: exact origins only; no cookies or wildcard."""
import os


def with_cors(application):
    def wrapped(environ, start_response):
        origin = environ.get('HTTP_ORIGIN', '')
        allowed = {v.strip() for v in os.getenv(
            'ALLOWED_ORIGINS', 'https://nikita2272282299.github.io'
        ).split(',') if v.strip()}
        api = environ.get('PATH_INFO', '').startswith('/api/')
        same_origin = environ.get('wsgi.url_scheme', 'https') + '://' + environ.get('HTTP_HOST', '')
        if origin == same_origin:
            allowed.add(origin)
        if api and origin and origin not in allowed:
            start_response('403 Forbidden', [('Content-Length', '0')])
            return [b'']

        def respond(status, headers, exc_info=None):
            if api and origin in allowed:
                headers = list(headers) + [
                    ('Access-Control-Allow-Origin', origin),
                    ('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Content-Type'),
                    ('Vary', 'Origin'),
                ]
            return start_response(status, headers, exc_info)

        if api and environ.get('REQUEST_METHOD') == 'OPTIONS':
            respond('204 No Content', [('Content-Length', '0')])
            return [b'']
        return application(environ, respond)
    return wrapped
