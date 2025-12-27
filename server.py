from mcp.server.fastmcp import FastMCP
import requests
import urllib.parse
import os
import json

# 1. 서버 이름 및 키 설정
mcp = FastMCP("BusRam")

# 공공데이터포털의 Decoding Key를 입력하세요
DECODING_KEY = "ezGwhdiNnVtd+HvkfiKgr/Z4r+gvfeUIRz/dVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI+/pJFoYr9Ce+TDg=="

# 2. 도구 정의 (Tools)
@mcp.tool(description="정류장 이름을 검색해서 ID와 ARS 번호를 찾습니다.")
def search_station(keyword: str) -> str:
    print(f"[Tool Exec] search_station called. Keyword: {keyword}")
    
    url = "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/getSttnNoList"
    params = {
        "serviceKey": DECODING_KEY,
        "cityCode": "11",
        "nodeNm": keyword,
        "numOfRows": 5,
        "_type": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"[API Response] Status Code: {response.status_code}")
        
        try: 
            data = response.json()
        except: 
            return f"Public Data API Error (Text): {response.text}"
        
        if 'response' not in data: 
            return f"API Error Structure: {data}"
        if data['response']['header']['resultCode'] != '00': 
            return "Public Data API Logic Error"
        if data['response']['body']['totalCount'] == 0: 
            return "No search results found."
        
        items = data['response']['body']['items']['item']
        if isinstance(items, dict): 
            items = [items]
        
        result = f"'{keyword}' Search Result:\n"
        for item in items:
            name = item.get('nodeNm')
            node_id = item.get('nodeid') 
            ars_id = item.get('nodeno')
            result += f"- {name} (ID: {node_id}) / ARS: {ars_id}\n"
        
        print(f"[Result] Found {len(items)} items")
        return result
    except Exception as e: 
        print(f"[Error] {e}")
        return f"Error: {str(e)}"

@mcp.tool(description="특정 정류장의 버스 도착 정보를 실시간으로 조회합니다.")
def check_arrival(city_code: str, station_id: str) -> str:
    print(f"[Tool Exec] check_arrival called. StationID: {station_id}")
    
    url = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList"
    params = {
        "serviceKey": DECODING_KEY,
        "cityCode": city_code,
        "nodeId": station_id,
        "numOfRows": 10,
        "_type": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        try: 
            data = response.json()
        except: 
            return f"Public Data API Error (Text): {response.text}"
        
        if 'response' not in data: 
            return f"API Error Structure: {data}"
        if data['response']['header']['resultCode'] != '00': 
            return "Public Data API Logic Error"
        if data['response']['body']['totalCount'] == 0: 
            return "No arrival info found."
        
        items = data['response']['body']['items']['item']
        if isinstance(items, dict): 
            items = [items]
        
        result = f"Bus Stop (ID:{station_id}) Arrival Info:\n"
        for item in items:
            bus = item.get('routeno') 
            left_stat = item.get('arrprevstationcnt') 
            min_left = int(item.get('arrtime')) // 60
            result += f"- [{bus}] {min_left} min left ({left_stat} stops)\n"
        return result
    except Exception as e: 
        return f"Error: {str(e)}"

# 3. Starlette 서버 설정
# =================================================================
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

mcp_server = mcp._mcp_server
sse = SseServerTransport("/mcp")

async def handle_sse_connect(request):
    client_ip = request.client.host
    print(f"[GET /mcp] Connection attempt from IP: {client_ip}")
    
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())

async def handle_sse_message(request):
    client_ip = request.client.host
    session_id = request.query_params.get("session_id")
    
    print(f"[POST /mcp] Message received from IP: {client_ip}")
    print(f"[Session ID] {session_id}")

    # PlayMCP Health Check 대응 (Session ID가 없으면 200 OK 반환)
    if not session_id:
        print("[PlayMCP Health Check] No Session ID -> Returning 200 OK")
        return JSONResponse({"status": "healthy"}, status_code=200)

    try:
        print("[Processing] Handling message...")
        await sse.handle_post_message(request.scope, request.receive, request._send)
        print("[Success] Message handled")
    except Exception as e:
        print(f"[Error] Message handling failed: {e}")

async def handle_root(request):
    print("[GET /] Root path accessed")
    return JSONResponse({"status": "ok", "service": "BusRam MCP"})

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = Starlette(
    debug=True,
    routes=[
        Route("/mcp", endpoint=handle_sse_connect, methods=["GET"]),
        Route("/mcp", endpoint=handle_sse_message, methods=["POST"]),
        Route("/", endpoint=handle_root, methods=["GET"])
    ],
    middleware=middleware
)