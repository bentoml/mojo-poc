from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import httpx

def create_app(target_url: str):
    app = FastAPI()
    client = httpx.AsyncClient(base_url=target_url)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    async def reverse_proxy(request: Request, path: str):
        url = httpx.URL(path=path, query=request.url.query.encode("utf-8"))
        
        headers = dict(request.headers)
        # The host header must be removed or the request will fail
        headers.pop("host", None)
        
        rp_req = client.build_request(
            request.method, url, headers=headers, content=request.stream()
        )
        
        try:
            rp_resp = await client.send(rp_req, stream=True)
        except httpx.ConnectError:
            return Response(status_code=502)
        except httpx.RequestError:
            return Response(status_code=500)

        return StreamingResponse(
            rp_resp.aiter_raw(),
            status_code=rp_resp.status_code,
            headers=rp_resp.headers,
            background=rp_resp.aclose,
        )

    return app
