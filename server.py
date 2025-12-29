# =================================================================
# BusRam MCP Server (Stateless HTTP / JSON-RPC Version)
# =================================================================
import uvicorn
import requests
import urllib.parse
import os
import json
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# 1. 설정 및 키
# -----------------------------------------------------------------
# ⚠️ 주의: Render 환경변수에 DECODING_KEY가 없다면 아래 문자열이 사용됩니다.
# (보안을 위해 실제 배포시엔 Render Environment Variables에 키를 넣는 것을 추천합니다)
DECODING_KEY = os.environ.get("DECODING_KEY", "ezGwhdiNnVtd+HvkfiKgr/Z4r+gvfeUIRz/dVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI+/pJFoYr9Ce+TDg==")

# 2. 도구(Tool) 실제 함수 정의
# -----------------------------------------------------------------
# ❌ 수정됨: @mcp.tool 데코레이터 삭제함 (이제 필요 없음)
def search_station(keyword: str, city_code: str = "11") -> str:
    print(f"[Tool] 정류장 검색: {keyword}, 도시코드: {city_code}")
    url = "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/getSttnNoList"
    
    # ✅ 수정됨: SERVICE_KEY -> DECODING_KEY로 변수명 통일
    params = {
        "serviceKey": DECODING_KEY, 
        "cityCode": city_code, 
        "nodeNm": keyword, 
        "numOfRows": 5, 
        "_type": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        
        # 디버깅: 실제로 호출된 URL 확인
        print(f"[Debug] 요청 URL: {response.url}") 
        
        try: data = response.json()
        except: return f"Error: {response.text}"
        
        if 'response' not in data: return f"API Error: {data}"
        
        if data['response']['body']['totalCount'] == 0: 
            return f"검색 결과가 없습니다. (도시코드 '{city_code}'에서 '{keyword}'를 찾지 못함. 도시코드를 변경해보세요.)"
        
        items = data['response']['body']['items']['item']
        if isinstance(items, dict): items = [items]
        
        result = f"🔍 '{keyword}' 검색 결과 (도시코드 {city_code}):\n"
        for item in items:
            result += f"- {item.get('nodeNm')} (ID: {item.get('nodeid')})\n"
        return result
    except Exception as e: return f"Error: {str(e)}"


def check_arrival(city_code: str, station_id: str) -> str:
    """특정 정류장의 버스 도착 정보를 실시간으로 조회합니다."""
    print(f"[Tool Exec] check_arrival: {station_id}")
    url = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList"
    
    # ✅ 수정됨: DECODING_KEY 사용 확인
    params = {"serviceKey": DECODING_KEY, "cityCode": city_code, "nodeId": station_id, "numOfRows": 10, "_type": "json"}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        try: data = response.json()
        except: return f"Error parsing JSON: {response.text}"
        
        if 'response' not in data: return f"API Error: {data}"
        if data['response']['body']['totalCount'] == 0: return "도착 정보 없음"
        
        items = data['response']['body']['items']['item']
        if isinstance(items, dict): items = [items]
        
        result = f"🚌 정류장(ID:{station_id}) 도착 정보:\n"
        for item in items:
            min_left = int(item.get('arrtime')) // 60
            result += f"- [{item.get('routeno')}번] {min_left}분 후\n"
        return result
    except Exception as e: return f"Error: {str(e)}"

# 3. 도구 등록부 (카카오에게 보여줄 메뉴판)
# -----------------------------------------------------------------
TOOLS = [
    {
        "name": "search_station",
        "description": "정류장 이름을 검색해서 ID와 ARS 번호를 찾습니다. 사용자가 '강남역' 등을 물어볼 때 사용합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "검색할 정류장 이름 (예: 강남역)"},
                "city_code": {"type": "string", "description": "도시 코드 (서울: 11, 경기: 12)"}
            },
            "required": ["keyword"]
        },
        "func": search_station
    },
    {
        "name": "check_arrival",
        "description": "특정 정류장의 버스 도착 정보를 실시간으로 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city_code": {"type": "string", "description": "도시 코드 (서울: 11)"},
                "station_id": {"type": "string", "description": "정류장 ID"}
            },
            "required": ["city_code", "station_id"]
        },
        "func": check_arrival
    }
]

# 4. JSON-RPC 처리 로직
# -----------------------------------------------------------------
async def handle_mcp_request(request):
    try:
        body = await request.json()
        method = body.get("method")
        msg_id = body.get("id")
        
        print(f"[POST] Method: {method}")

        if method == "initialize":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "BusRam", "version": "1.0.0"}
                }
            })

        elif method == "tools/list":
            # func 키를 제외하고 전송
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]
                }
            })

        elif method == "tools/call":
            params = body.get("params", {})
            tool_name = params.get("name")
            args = params.get("arguments", {})
            
            tool = next((t for t in TOOLS if t["name"] == tool_name), None)
            
            if tool:
                try:
                    # 함수 실행
                    result_text = tool["func"](**args)
                    return JSONResponse({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": result_text}],
                            "isError": False
                        }
                    })
                except Exception as e:
                    return JSONResponse({
                        "jsonrpc": "2.0", 
                        "id": msg_id, 
                        "result": {
                            "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                            "isError": True
                        }
                    })
            else:
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})

        else:
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

async def handle_root(request):
    return JSONResponse({"status": "ok", "service": "BusRam MCP (Stateless)"})

# 5. 서버 실행
# -----------------------------------------------------------------
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
        Route("/mcp", endpoint=handle_mcp_request, methods=["POST"]),
        Route("/", endpoint=handle_root, methods=["GET"])
    ],
    middleware=middleware
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)