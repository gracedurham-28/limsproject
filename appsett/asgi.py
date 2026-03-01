"""
ASGI config for appsett project.

It exposes the ASGI callable as a module-level variable named ``application``.

If Django is not importable in the current environment (editor/analysis tools or wrong Python),
this module will expose a small fallback ASGI application that returns a 500 response with a
helpful message. In normal use (project venv or Docker) Django will be imported and the
real ASGI application will be returned.
"""

import os
import importlib.util

PROJECT_SETTINGS = 'appsett.settings'


def _fallback_app(scope, receive, send):
    """Minimal ASGI app used when Django is not available.
    Responds to HTTP requests with a 500 status and a short plain-text message.
    """
    async def app_inner():
        if scope.get('type') != 'http':
            # for non-http scopes do nothing
            return
        await send({
            'type': 'http.response.start',
            'status': 500,
            'headers': [(b'content-type', b'text/plain; charset=utf-8')],
        })
        body = (
            b"Django is not available in this Python environment.\n"
            b"Activate the project virtualenv (limsenv) or run via Docker before starting the app."
        )
        await send({'type': 'http.response.body', 'body': body})

    return app_inner()


# Only import Django if the module is available in this interpreter; avoids import-time
# failures in editors or when the wrong Python is used.
if importlib.util.find_spec('django.core.asgi') is not None:
    # Set settings module before creating the application
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', PROJECT_SETTINGS)
    try:
        django_asgi_mod = importlib.import_module('django.core.asgi')
        get_asgi_application = getattr(django_asgi_mod, 'get_asgi_application')
        application = get_asgi_application()
    except Exception:
        # If import fails for any reason, fall back to the minimal app
        application = _fallback_app
else:
    # Provide the fallback app to avoid crashes and give a helpful message at runtime.
    application = _fallback_app

# Note: when running under the correct environment (limsenv) or in Docker this will
# return the real Django ASGI application. The fallback is only used when Django is
# not importable in the current interpreter.
