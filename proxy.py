import uvicorn
import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: Starlette):
    """
    Manage the lifespan of the httpx client.
    The client is created on startup and closed on shutdown.
    """
    async with httpx.AsyncClient() as client:
        app.state.client = client
        yield
        # Clean up the client resources
        # (httpx.AsyncClient as context manager handles this automatically)

def create_app(target: str) -> Starlette:
    """
    Creates a Starlette application that proxies requests to the given target.
    """
    async def proxy(request: Request):
        """
        Proxies the incoming request to the target server.
        """
        client: httpx.AsyncClient = request.app.state.client

        # Construct the full target URL.
        url = httpx.URL(target).join(request.url.path)
        url = url.copy_with(raw_path=request.url.query.encode("utf-8"))

        # Filter out hop-by-hop headers that shouldn't be forwarded.
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() not in ("host",)
        }

        # Build the request to the upstream server, streaming the body.
        rp_req = client.build_request(
            method=request.method,
            url=url,
            headers=headers,
            content=request.stream(),
        )

        # Send the request and get a streaming response.
        rp_resp = await client.send(rp_req, stream=True)

        # Filter hop-by-hop headers from the response.
        response_headers = {
            name: value
            for name, value in rp_resp.headers.items()
            if name.lower() not in ("content-encoding", "content-length", "transfer-encoding")
        }
        
        return StreamingResponse(
            rp_resp.aiter_bytes(),
            status_code=rp_resp.status_code,
            headers=response_headers,
        )

    routes = [
        Route("/{path:path}", endpoint=proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    ]

    return Starlette(routes=routes, lifespan=lifespan)

if __name__ == "__main__":
    # The target server to proxy requests to.
    # Remember to change this to your actual target server.
    TARGET_SERVER = "https://www.google.com"
    app = create_app(TARGET_SERVER)
    uvicorn.run(app, host="0.0.0.0", port=8000)
