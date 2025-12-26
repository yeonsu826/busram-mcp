from mcp.server.fastmcp import FastMCP
import requests
import urllib.parse
import os

# 1. 서버 이름 설정
mcp = FastMCP("BusAlert")

# 2. 키 설정
ENCODING_KEY = "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D"
DECODING_KEY = urllib.parse.unquote(ENCODING_KEY)

@mcp.tool()
def search_station(keyword: str) -> str:
    """[1단계] 정류장 이름을 검색해서 ID를 찾습니다."""
    base_url = "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/getSttnNoList"
    url = f"{base_url}?serviceKey={ENCODING_KEY}&cityCode=11&nodeNm={keyword}&numOfRows=5&_type=json"
    try:
        response = requests.get(url, timeout=10)
        try: data = response.json()
        except: return f"공공데이터 오류: {response.text}"
        if 'response' not in data: return f"API 에러: {data}"
        if data['response']['header']['resultCode'] != '00': return "공공데이터 에러"
        if data['response']['body']['totalCount'] == 0: return "검색 결과 없음"
        items = data['response']['body']['items']['item']
        if isinstance(items, dict): items = [items]
        result = f"🔍 '{keyword}' 검색 결과:\n"
        for item in items:
            name = item.get('nodeNm')
            node_id = item.get('nodeid') 
            ars_id = item.get('nodeno')
            result += f"- {name} (ID: {node_id}) / 정류장번호: {ars_id}\n"
        return result
    except Exception as e: return f"에러: {str(e)}"

@mcp.tool()
def check_arrival(city_code: str, station_id: str) -> str:
    """[2단계] 도착 정보 조회"""
    base_url = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList"
    url = f"{base_url}?serviceKey={ENCODING_KEY}&cityCode={city_code}&nodeId={station_id}&numOfRows=10&_type=json"
    try:
        response = requests.get(url, timeout=10)
        try: data = response.json()
        except: return f"공공데이터 오류: {response.text}"
        if 'response' not in data: return f"API 에러: {data}"
        if data['response']['header']['resultCode'] != '00': return "공공데이터 에러"
        if data['response']['body']['totalCount'] == 0: return "도착 예정 버스 없음"
        items = data['response']['body']['items']['item']
        if isinstance(items, dict): items = [items]
        result = f"🚌 정류장(ID:{station_id}) 도착 정보:\n"
        for item in items:
            bus = item.get('routeno') 
            left_stat = item.get('arrprevstationcnt') 
            min_left = int(item.get('arrtime')) // 60
            result += f"- [{bus}번] {min_left}분 후 도착 ({left_stat}정거장 전)\n"
        return result
    except Exception as e: return f"에러: {str(e)}"

# =================================================================
# 👇 [만능 접속 코드] /sse, /messages 모두 허용 + 로그 출력
# =================================================================
if __name__ == "__main__":
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.responses import JSONResponse

    server = mcp._mcp_server
    sse = SseServerTransport("/sse")

    async def handle_sse_connect(request):
        print(f"🔌 [접속 감지] 누군가 연결을 시도합니다! (GET {request.url.path})")
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    async def handle_sse_message(request):
        print(f"📩 [메시지 수신] 명령이 들어왔습니다! (POST {request.url.path})")
        await sse.handle_post_message(request.scope, request.receive, request._send)

    async def handle_root(request):
        print(f"👋 [헬스 체크] 루트 경로 접속 (GET /)")
        return JSONResponse({"status": "ok", "message": "BusRam MCP is live!"})

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    starlette_app = Starlette(
        debug=True,
        routes=[
            Route("/sse", endpoint=handle_sse_connect, methods=["GET"]),
            Route("/sse", endpoint=handle_sse_message, methods=["POST"]),
            # 👇 혹시 /messages로 찌를까봐 이것도 열어둠
            Route("/messages", endpoint=handle_sse_message, methods=["POST"]),
            Route("/", endpoint=handle_root, methods=["GET"])
        ],
        middleware=middleware
    )

    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 만능 서버 시작! (0.0.0.0:{port})")
    # proxy_headers=True 추가 (Render 같은 클라우드 환경 필수)
    uvicorn.run(starlette_app, host="0.0.0.0", port=port, proxy_headers=True)