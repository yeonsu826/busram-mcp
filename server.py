# =================================================================
# BusRam MCP Server (CSV Hybrid Version)
# =================================================================
import uvicorn
import requests
import pandas as pd  # pandas 추가 (requirements.txt에 있어야 함)
import os
import json
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# 1. 설정 및 CSV 데이터 로드 (서버 시작 시 1회 실행)
# -----------------------------------------------------------------
# ⚠️ 본인의 [Encoding] 인증키를 여기에 넣으세요 (URL에 직접 붙일 용도)
DECODING_KEY = os.environ.get("DECODING_KEY", "ezGwhdiNnVtd+HvkfiKgr/Z4r+gvfeUIRz/dVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI+/pJFoYr9Ce+TDg==")


print("📂 [System] 정류장 데이터(CSV) 로딩 중...")
CSV_PATH = "국토교통부_전국 버스정류장 위치정보_20251031.csv"

try:
    # 1. CSV 읽기 (인코딩 자동 감지 시도)
    try:
        df_stations = pd.read_csv(CSV_PATH, encoding='cp949')
    except:
        df_stations = pd.read_csv(CSV_PATH, encoding='utf-8')

    # 2. 데이터 전처리 (검색 속도를 위해 문자열로 변환)
    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    df_stations['도시코드'] = df_stations['도시코드'].astype(str)
    df_stations['정류장번호'] = df_stations['정류장번호'].astype(str) # 이게 API용 ID (nodeId)
    
    print(f"✅ [System] 데이터 로드 완료! 총 {len(df_stations)}개 정류장 대기 중.")

except Exception as e:
    print(f"❌ [Critical] CSV 파일 로드 실패: {e}")
    print("👉 '국토교통부_전국 버스정류장 위치정보_20251031.csv' 파일이 같은 폴더에 있는지 확인하세요.")
    df_stations = pd.DataFrame() # 빈 껍데기 생성 (서버 다운 방지)


# 2. 도구(Tool) 함수 정의
# -----------------------------------------------------------------
def get_bus_arrival(keyword: str) -> str:
    """
    정류장 이름(예: '강남역', '판교역')을 입력받아,
    CSV에서 ID를 찾고 -> 실시간 도착 정보를 조회해줍니다.
    """
    print(f"[Tool] '{keyword}' 검색 및 도착정보 조회 시작")
    
    if df_stations.empty:
        return "❌ 서버 에러: 정류장 데이터 파일(CSV)이 로드되지 않았습니다."

    # [Step 1] CSV에서 정류장 검색 (이름에 키워드가 포함된 것 찾기)
    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask]
    
    if results.empty:
        return f"❌ '{keyword}' 검색 결과가 없습니다. 정류장 이름을 확인해주세요."
    
    # 결과가 너무 많으면 상위 3개만 조회 (속도 최적화)
    targets = results.head(3)
    final_output = f"🚏 '{keyword}' 관련 정류장 도착 정보:\n"
    
    # [Step 2] 찾은 정류장 ID로 API 호출
    api_url = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList"
    
    for _, row in targets.iterrows():
        station_name = row['정류장명']
        station_id = row['정류장번호']  # CSV에서 꺼낸 ID (nodeId)
        city_code = row['도시코드']     # CSV에서 꺼낸 도시코드
        
        final_output += f"\n📍 {station_name} (ID: {station_id})\n"
        
        # Requests가 키를 망가뜨리지 않게 URL에 직접 붙임
        request_url = f"{api_url}?serviceKey={ENCODING_KEY}"
        params = {
            "cityCode": city_code,
            "nodeId": station_id,
            "numOfRows": 5,
            "_type": "json"
        }
        
        try:
            response = requests.get(request_url, params=params, timeout=5)
            
            try: data = response.json()
            except: 
                final_output += "   - (데이터 조회 실패: API 응답 오류)\n"
                continue

            if data['response']['body']['totalCount'] == 0:
                final_output += "   💤 현재 도착 예정인 버스가 없습니다.\n"
                continue
                
            items = data['response']['body']['items']['item']
            if isinstance(items, dict): items = [items]
            
            for bus in items:
                route_no = bus.get('routeno') # 버스 번호
                arr_time = bus.get('arrtime') # 남은 시간(초)
                min_left = int(arr_time) // 60
                msg = bus.get('arrmsg1', '')  # "곧 도착" 등 메시지
                
                final_output += f"   🚌 [{route_no}번] {min_left}분 후 도착 ({msg})\n"
                
        except Exception as e:
            final_output += f"   - ⚠️ 에러 발생: {str(e)}\n"
            
    return final_output


# 3. 도구 등록부 (카카오에게 보여줄 메뉴판)
# -----------------------------------------------------------------
TOOLS = [
    {
        "name": "get_bus_arrival",
        "description": "정류장 이름(예: 서울역, 강남역)을 검색하면, 해당 정류장에 곧 도착하는 버스 정보를 알려줍니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "검색할 정류장 이름 (예: 강남역)"}
            },
            "required": ["keyword"]
        },
        "func": get_bus_arrival
    }
]

# 4. JSON-RPC 처리 로직 (수정할 필요 없음)
# -----------------------------------------------------------------
async def handle_mcp_request(request):
    try:
        body = await request.json()
        method = body.get("method")
        msg_id = body.get("id")
        print(f"[POST] Method: {method}")

        if method == "initialize":
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "BusRam", "version": "1.0.0"}
                }
            })

        elif method == "tools/list":
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]}
            })

        elif method == "tools/call":
            params = body.get("params", {})
            tool_name = params.get("name")
            args = params.get("arguments", {})
            tool = next((t for t in TOOLS if t["name"] == tool_name), None)
            
            if tool:
                try:
                    result_text = tool["func"](**args)
                    return JSONResponse({
                        "jsonrpc": "2.0", "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": result_text}],
                            "isError": False
                        }
                    })
                except Exception as e:
                    return JSONResponse({
                        "jsonrpc": "2.0", "id": msg_id, 
                        "result": {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}
                    })
            else:
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})
        else:
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def handle_root(request):
    return JSONResponse({"status": "ok", "service": "BusRam MCP (CSV Hybrid)"})

middleware = [Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]

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