"""Production entrypoint: the API and the built React app from one process.

    uvicorn server:app --host 0.0.0.0 --port $PORT

Layout:

    /health      status report for the host's health check
    /api/*       the FastAPI application from main.py, unchanged
    /*           the React build (static files, falling back to index.html)

Serving both from one origin is what makes the deployment simple: there is
one URL, one container, and no CORS at all, because the browser is never
making a cross-origin request. Local development is untouched — keep running
`uvicorn main:app --reload` and `npm start` as before.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route

log = logging.getLogger("server")

STATIC_DIR = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parent / "static"))

# Content-hashed by the build, so they can be cached for as long as we like.
IMMUTABLE = "public, max-age=31536000, immutable"
# index.html and friends name those hashed files, so they must be revalidated
# or a browser keeps asking for a bundle that no longer exists after a deploy.
REVALIDATE = "no-cache"


class SecurityHeaders:
    """Adds the response headers every page should carry. Plain ASGI, so it
    costs nothing and never buffers a response body."""

    def __init__(self, app, *, hsts: bool) -> None:
        self.app = app
        headers = {
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "strict-origin-when-cross-origin",
            "permissions-policy": "camera=(), geolocation=(), payment=()",
        }
        if hsts:
            headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
        self.headers = [(k.encode(), v.encode()) for k, v in headers.items()]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                present = {name for name, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    (k, v) for k, v in self.headers if k not in present
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)


def create_app(api_app, *, lifespan=None, health=None, static_dir: Path = STATIC_DIR,
               hsts: bool = False) -> Starlette:
    static_root = Path(static_dir).resolve()
    index = static_root / "index.html"
    has_frontend = index.is_file()

    async def health_route(request: Request) -> Response:
        if health is None:
            return JSONResponse({"status": "ok"})
        # health() pings the database, which blocks; keep it off the loop.
        return JSONResponse(await run_in_threadpool(health))

    async def spa(request: Request) -> Response:
        if not has_frontend:
            return PlainTextResponse(
                "MindWell API is running. The web app is not bundled in this "
                "build; the API is under /api.",
                status_code=200,
            )

        relative = request.path_params.get("path", "")
        if relative:
            candidate = (static_root / relative).resolve()
            # resolve() collapses any "..", so this containment check is what
            # stops /../../etc/passwd from leaving the build directory.
            if candidate.is_file() and static_root in candidate.parents:
                cache = IMMUTABLE if relative.startswith("static/") else REVALIDATE
                return FileResponse(candidate, headers={"cache-control": cache})
            # A missing asset must be a real 404. Answering index.html for a
            # missing .js file makes the browser try to execute HTML.
            if "." in relative.rsplit("/", 1)[-1]:
                return PlainTextResponse("Not found", status_code=404)

        return FileResponse(index, headers={"cache-control": REVALIDATE})

    routes = [
        Route("/health", health_route, methods=["GET", "HEAD"]),
        Mount("/api", app=api_app),
        Route("/", spa, methods=["GET", "HEAD"]),
        Route("/{path:path}", spa, methods=["GET", "HEAD"]),
    ]

    if not has_frontend:
        log.warning("No frontend build at %s; serving the API only", static_root)

    return Starlette(
        routes=routes,
        lifespan=lifespan,
        middleware=[
            Middleware(SecurityHeaders, hsts=hsts),
            Middleware(GZipMiddleware, minimum_size=1024),
        ],
    )


def _build() -> Starlette:
    import main
    from config import settings

    return create_app(
        main.app,
        lifespan=main.lifespan,
        health=main.health,
        hsts=settings.IS_PRODUCTION,
    )


app = _build() if os.getenv("MINDWELL_SKIP_APP_BUILD") != "1" else None
