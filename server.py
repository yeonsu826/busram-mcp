# =================================================================
# BusRam MCP Server (Direction & ARS Update)
# =================================================================
import uvicorn
import requests
import pandas as pd
import os
import json
import re
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# 1. 설정 및 CSV 데이터 로드
# -----------------------------------------------------------------
# ⚠️ [Encoding] 키 확인
ENCODING_KEY = os.environ.get("ENCODING_KEY", "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D")

print("📂 [System] 정류장 데이터(CSV) 로딩 중...")
CSV_PATH = "station_data.csv"

try:
    try:
        df_stations = pd.read_csv(CSV_PATH, encoding='cp949')
    except:
        df_stations = pd.read_csv(CSV_PATH, encoding='utf-8')

    # 데이터 전처리
    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    df_stations['도시코드'] = df_stations['도시코드'].astype(str)
    df_stations['정류장번호'] = df_stations['정류장번호'].astype(str)
    
    print(f"✅ [System] 데이터 로드 완료! 총 {len(df_stations)}개 정류장 대기 중.")

except Exception as e:
    print(f"❌ [Critical] CSV 파일 로드 실패: {e}")
    df_stations = pd.DataFrame()


# 2. 도구(Tool) 함수 정의
# -----------------------------------------------------------------
def get_bus_arrival(keyword: str) -> str:
    """
    정류장 이름(예: '하림각')을 검색하여 방향별(다음 정류장) 도착 정보를 조회합니다.
    """
    print(f"[Tool] '{keyword}' 검색 시작")
    
    if df_stations.empty:
        return "❌ 서버 에러: CSV 파일 로드 실패"

    # 키워드 검색
    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask]
    
    if results.empty:
        return f"❌ '{keyword}' 검색 결과가 없습니다."
    
    # 너무 많으면 상위 4개까지만 (양방향 확인을 위해 조금 늘림)
    targets = results.head(4)
    final_output = f"🚏 '{keyword}' 검색 결과:\n"
    
    api_url = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList"
    
    for _, row in targets.iterrows():
        station_name = row['정류장명']
        raw_id = row['정류장번호']
        city_code = row['도시코드']
        
        # 🟢 [추가 1] ARS 번호 (정류장 표지판 숫자) 가져오기
        ars_raw = row.get('모바일단축번호', '')
        ars_str = ""
        try:
            if pd.notnull(ars_raw) and str(ars_raw).strip() != "":
                # 1234.0 처럼 실수로 나오는 경우 정수로 변환
                ars_num = int(float(ars_raw))
                ars_str = f"(ARS: {ars_num})"
        except:
            pass # 변환 실패하면 그냥 비워둠

        # ID에서 숫자만 추출
        station_id = re.sub(r'[^0-9]', '', raw_id)

        # 임시 헤더 (아직 다음 정류장을 모름)
        station_header = f"\n📍 {station_name} {ars_str} [ID: {station_id}]"
        bus_list_str = ""
        
        # API 호출
        request_url = f"{api_url}?serviceKey={ENCODING_KEY}"
        params = {
            "cityCode": city_code,
            "nodeId": station_id,
            "numOfRows": 10, # 넉넉하게 조회
            "_type": "json"
        }
        
        next_station_found = False # 다음 정류장 찾았는지 여부
        
        try:
            response = requests.get(request_url, params=params, timeout=5)
            
            # 응답 파싱
            try: data = response.json()
            except: 
                final_output += station_header + "\n   - (데이터 해석 실패)\n"
                continue

            if data['response']['body']['totalCount'] == 0:
                final_output += station_header + "\n   💤 도착 예정 버스 없음 (방향 확인 불가)\n"
                continue
                
            items = data['response']['body']['items']['item']
            if isinstance(items, dict): items = [items]
            
            # 버스 목록 만들기
            for bus in items:
                route_no = bus.get('routeno')
                arr_time = bus.get('arrtime')
                min_left = int(arr_time) // 60
                msg = bus.get('arrmsg1', '')
                
                # 🟢 [추가 2] API에서 '다음 정류장' 정보 훔쳐오기
                # (API마다 필드명이 다를 수 있어 여러 개 시도)
                if not next_station_found:
                    next_st = bus.get('nextSttnNm') # 국토부 표준
                    # 없으면 다른 필드 시도 (API 버전에 따라 다름)
                    if not next_st: next_st = bus.get('nextStationNm')
                    
                    if next_st and next_st != "null" and next_st != "":
                        # 헤더에 '다음 정류장' 정보를 추가해서 덮어씌움!
                        station_header = f"\n📍 {station_name} {ars_str} (👉 방향: {next_st})"
                        next_station_found = True

                bus_list_str += f"   🚌 [{route_no}번] {min_left}분 후 ({msg})\n"
                
            # 최종 출력에 추가
            final_output += station_header + "\n" + bus_list_str
                
        except Exception as e:
            final_output += station_header + f"\n   - ⚠️ 에러: {str(e)}\n"
            
    return final_output


# 3. 도구 등록부
# -----------------------------------------------------------------
TOOLS = [
    {
        "name": "get_bus_arrival",
        "description": "정류장 이름(예: 하림각)을 검색하면, 방향(다음 정류장) 정보와 함께 버스 도착 시간을 알려줍니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "검색할 정류장 이름"}
            },
            "required": ["keyword"]
        },
        "func": get_bus_arrival
    }
]

# 4. JSON-RPC 핸들러
# -----------------------------------------------------------------
async def handle_mcp_request(request):
    try:
        body = await request.json()
        method = body.get("method")
        msg_id = body.get("id")

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
                result_text = tool["func"](**args)
                return JSONResponse({
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {"content": [{"type": "text", "text": result_text}], "isError": False}
                })
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def handle_root(request):
    return JSONResponse({"status": "ok", "service": "BusRam MCP"})

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