"""Local integration preview under the same subpath as project Pages."""
from wsgiref.simple_server import make_server
from pa_wsgi import application


def mounted(environ, start_response):
    prefix = '/school-schedule'
    path = environ.get('PATH_INFO', '')
    if path.startswith(prefix + '/'):
        environ['PATH_INFO'] = path[len(prefix):]
        environ['SCRIPT_NAME'] = prefix
    return application(environ, start_response)


if __name__ == '__main__':
    server = make_server('127.0.0.1', 0, mounted)
    print(f'http://127.0.0.1:{server.server_port}/school-schedule/', flush=True)
    server.serve_forever()
