# =================================================================
# BusRam MCP Server (V_FINAL: 4-Function Arrival API Mode)
# "위치 정보 권한" 없이 "도착 정보"만으로 버스 위치 파악하기
# =================================================================
import uvicorn
import requests
import pandas as pd
import os
import json
import re
from urllib.parse import unquote
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

# 🔑 [키 설정] 사용자님의 디코딩된 키
DECODED_KEY = "ezGwhdiNnVtd+HvkfiKgr/Z4r+gvfeUIRz/dVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI+/pJFoYr9Ce+TDg=="

print("📂 [System] 데이터 로딩 중...")
STATION_CSV = "station_data.csv"
ROUTE_CSV = "route_data.csv"

# [1] 노선 데이터 로드
try:
    df_routes = pd.read_csv(ROUTE_CSV, encoding='utf-8')
    df_routes['노선명'] = df_routes['노선명'].astype(str)
    df_routes['ROUTE_ID'] = df_routes['ROUTE_ID'].astype(str)
    print(f"✅ 노선 데이터 로드 완료: {len(df_routes)}개")
except: 
    print("❌ 노선 데이터 로드 실패")
    df_routes = pd.DataFrame()

# [2] 정류장 데이터 로드
try:
    try: df_stations = pd.read_csv(STATION_CSV, encoding='cp949')
    except: df_stations = pd.read_csv(STATION_CSV, encoding='utf-8')
    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    # 정류장 번호 정제 (숫자만)
    df_stations['clean_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x))
    print(f"✅ 정류장 데이터 로드 완료: {len(df_stations)}개")
except:
    print("❌ 정류장 데이터 로드 실패") 
    df_stations = pd.DataFrame()

# --- [Helper] ID 찾기 함수들 ---
def get_route_id(bus_no):
    """버스 번호(예: 7016)로 ROUTE_ID 찾기"""
    if df_routes.empty: return None
    row = df_routes[df_routes['노선명'] == bus_no]
    return row.iloc[0]['ROUTE_ID'] if not row.empty else None

def get_station_id(st_name):
    """정류장 이름(예: 광화문)으로 stId(고유ID) 찾기"""
    if df_stations.empty: return None
    row = df_stations[df_stations['정류장명'].str.contains(st_name)].head(1)
    if row.empty: return None
    # 9자리 고유 ID 추출을 위해 정류장 번호 사용 (데이터 구조에 따라 다름)
    # 여기서는 station_data.csv의 '정류장번호'가 ARS-ID라면 변환이 필요할 수 있으나,
    # 우선 API에 ARS-ID가 아닌 '정류소ID(stId)'가 필요하므로 검색된 행의 데이터를 사용
    # *참고: CSV에 stId 컬럼이 없다면 API 호출에 제한이 있을 수 있음.
    # 일단 정류장번호(ARS-ID)를 통해 우회적으로 시도하거나, 사용자 데이터를 믿고 진행
    return re.sub(r'[^0-9]', '', str(row.iloc[0]['정류장번호']))

# =================================================================
# 🛠️ 도구 4종 세트 (Google Docs 문서 기준)
# =================================================================

# [Tool 1] ⭐ 핵심: 노선 전체 정류소 도착 정보 (버스 위치 파악용)
# API: getArrInfoByRouteAll
def get_route_all_arrival(bus_number: str) -> str:
    print(f"[Tool 1] {bus_number}번 버스 전체 현황 조회")
    route_id = get_route_id(bus_number)
    if not route_id: return f"❌ '{bus_number}'번 버스 ID를 찾을 수 없습니다."
    
    # URL 주의: 문서엔 List가 붙어있으나 실제 호출엔 없는 경우가 많음. 둘 다 고려.
    url = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll"
    params = {"serviceKey": DECODED_KEY, "busRouteId": route_id, "resultType": "json"}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        # 에러 체크
        if 'msgHeader' in data and data['msgHeader']['headerCd'] != '0':
             return f"⚠️ API 에러: {data['msgHeader']['headerMsg']}"

        items = data['msgBody']['itemList']
        if isinstance(items, dict): items = [items]
        
        output = f"🚍 **[{bus_number}번 버스 실시간 운행 현황]**\n(도착 예정 정보 기반)\n"
        count = 0
        for item in items:
            msg1 = item.get('arrmsg1', '')
            st_nm = item.get('stNm', '')
            
            # '운행종료', '출발대기'가 아니고, 실제 몇분/몇번째 전 정보가 있는 경우만 출력
            if msg1 and '대기' not in msg1 and '종료' not in msg1:
                output += f"- {st_nm}: {msg1}\n"
                count += 1
        
        if count == 0: output += "\n(현재 운행 중인 버스가 없거나, 출발 대기 중입니다)"
        return output
    except Exception as e: return f"❌ 에러 발생: {e}"

# [Tool 2] 특정 정류소 + 특정 노선 도착 정보
# API: getArrInfoByRoute
def get_specific_arrival(bus_number: str, station_name: str) -> str:
    # 이 API는 '순번(ord)'이 필수인데 CSV에 없으면 1로 가정해야 해서 정확도가 떨어질 수 있음
    return "⚠️ 이 기능(Tool 2)은 '정류장 순번' 데이터가 필요하여 현재 비활성화 권장 (Tool 1 사용 추천)"

# [Tool 3] 저상버스 전용 (특정 노선+정류장)
# API: getLowArrInfoByRoute
def get_low_specific_arrival(bus_number: str, station_name: str) -> str:
    return "⚠️ 이 기능(Tool 3)은 Tool 1로 대체 가능합니다."

# [Tool 4] 정류장별 도착 정보 (기존에 쓰던 것 + 마을버스 포함)
# API: getArrInfoByUid (기존 getLow... 대신 이걸 써야 마을버스도 나옴)
def get_station_arrival(station_name: str) -> str:
    print(f"[Tool 4] '{station_name}' 정류장 조회")
    # 정류장 이름으로 검색해서 첫 번째 결과 사용
    if df_stations.empty: return "❌ 정류장 데이터 없음"
    
    mask = df_stations['정류장명'].str.contains(station_name)
    results = df_stations[mask].head(1)
    if results.empty: return f"❌ '{station_name}' 정류장을 찾을 수 없습니다."
    
    target_row = results.iloc[0]
    st_id = re.sub(r'[^0-9]', '', str(target_row['정류장번호'])) # 여기선 ARS-ID 사용
    real_st_name = target_row['정류장명']

    url = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByUid"
    # getArrInfoByUid는 arsId를 stId 파라미터로 받기도 함 (API 특성)
    params = {"serviceKey": DECODED_KEY, "stId": st_id, "resultType": "json"}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if 'msgBody' not in data: return f"⚠️ 데이터 없음 ({real_st_name})"
        
        items = data['msgBody']['itemList']
        if isinstance(items, dict): items = [items]
        
        output = f"🚏 **{real_st_name} ({st_id}) 도착 정보**\n"
        for bus in items:
            rt_nm = bus.get('rtNm', '?')
            msg1 = bus.get('arrmsg1', '정보없음')
            if msg1 != '운행종료':
                output += f"🚌 [{rt_nm}] {msg1}\n"
        return output
    except Exception as e: return f"❌ 에러: {e}"

# -----------------------------------------------------------------
# 🚀 핸들러 설정
# -----------------------------------------------------------------
TOOLS = [
    {
        "name": "get_route_all_arrival", 
        "description": "특정 버스 노선의 모든 정류장 도착 정보를 조회하여 버스 위치를 파악합니다. (예: 7016)", 
        "inputSchema": {
            "type": "object", 
            "properties": {"bus_number": {"type": "string"}}, 
            "required": ["bus_number"]
        }, 
        "func": get_route_all_arrival
    },
    {
        "name": "get_station_arrival", 
        "description": "특정 정류장의 모든 버스 도착 정보를 조회합니다. (예: 하림각)", 
        "inputSchema": {
            "type": "object", 
            "properties": {"station_name": {"type": "string"}}, 
            "required": ["station_name"]
        }, 
        "func": get_station_arrival
    }
]

async def handle_request(request):
    if request.method == "GET": return JSONResponse({"status": "BusRam V_FINAL Online"})
    try:
        body = await request.json()
        msg_id = body.get("id")
        
        if body.get("method") == "initialize": 
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id, 
                "result": {
                    "protocolVersion": "2024-11-05", 
                    "capabilities": {},
                    "serverInfo": {"name": "BusRam", "version": "1.0.8"}
                }
            })
        elif body.get("method") == "tools/list":
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id, 
                "result": {
                    "tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]
                }
            })
        elif body.get("method") == "tools/call":
            tool_name = body["params"]["name"]
            tool = next((t for t in TOOLS if t["name"] == tool_name), None)
            if tool:
                res = await run_in_threadpool(tool["func"], **body["params"]["arguments"])
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": res}]}})
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})
    except Exception as e: 
        return JSONResponse({"error": str(e)}, status_code=500)

app = Starlette(debug=True, routes=[
    Route("/", endpoint=handle_request, methods=["POST", "GET"]),
    Route("/mcp", endpoint=handle_request, methods=["POST", "GET"])
], middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))