import aiohttp
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

def create_app(target: str) -> Starlette:
    """
    Creates a Starlette application that proxies requests to the given target.
    """
    async def proxy(request: Request):
        """
        Proxies the incoming request to the target server.
        """
        async with aiohttp.ClientSession() as session:
            # Construct the target URL
            path = request.url.path
            query = request.url.query
            target_url = f"{target}{path}"
            if query:
                target_url += f"?{query}"

            # Stream the request body
            async def stream_request_body():
                async for chunk in request.stream():
                    yield chunk

            # Forward the request
            async with session.request(
                method=request.method,
                url=target_url,
                headers=request.headers,
                data=stream_request_body(),
                allow_redirects=False
            ) as resp:
                # Stream the response back to the client
                async def stream_response_body():
                    async for chunk in resp.content.iter_any():
                        yield chunk

                return StreamingResponse(
                    stream_response_body(),
                    status_code=resp.status,
                    headers=resp.headers
                )

    routes = [
        Route("/{path:path}", endpoint=proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    ]

    return Starlette(routes=routes)

if __name__ == "__main__":
    # The target server to proxy requests to.
    # Remember to change this to your actual target server.
    TARGET_SERVER = "https://www.google.com"
    app = create_app(TARGET_SERVER)
    uvicorn.run(app, host="0.0.0.0", port=8000)
