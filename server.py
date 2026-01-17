# =================================================================
# BusRam MCP Server (V22: Tool 3 Added for Testing getArrInfoByUid)
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

# 🔑 [키 설정]
DECODED_KEY = "ezGwhdiNnVtd+HvkfiKgr/Z4r+gvfeUIRz/dVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI+/pJFoYr9Ce+TDg=="

print("📂 [System] 데이터 로딩 중...")
STATION_CSV = "station_data.csv"
ROUTE_CSV = "route_data.csv"

# [1] 데이터 로드 및 ID 매핑 준비
try:
    df_routes = pd.read_csv(ROUTE_CSV, encoding='utf-8')
    df_routes['노선명'] = df_routes['노선명'].astype(str)
    df_routes['ROUTE_ID'] = df_routes['ROUTE_ID'].astype(str)
    df_routes['순번'] = pd.to_numeric(df_routes['순번'], errors='coerce').fillna(0).astype(int)
    df_routes['ARS_ID'] = df_routes['ARS_ID'].astype(str).apply(lambda x: x.split('.')[0].zfill(5))
except: df_routes = pd.DataFrame()

try:
    try: df_stations = pd.read_csv(STATION_CSV, encoding='cp949')
    except: df_stations = pd.read_csv(STATION_CSV, encoding='utf-8')
    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    
    # 1. API용 9자리 ID (stId)
    if '정류소ID' in df_stations.columns:
        df_stations['api_id'] = df_stations['정류소ID'].astype(str)
    elif 'NODE_ID' in df_stations.columns:
        df_stations['api_id'] = df_stations['NODE_ID'].astype(str)
    else:
        df_stations['api_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x))

    # 2. 사용자용 5자리 ARS ID (arsId)
    if '모바일단축번호' in df_stations.columns:
        df_stations['ars_id'] = df_stations['모바일단축번호'].fillna(0).astype(str).apply(lambda x: x.split('.')[0].zfill(5))
    else:
        df_stations['ars_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x)[-5:].zfill(5))

except: df_stations = pd.DataFrame()


# --- [Helper] 방향 찾기 함수 ---
def get_direction_from_csv(bus_no, current_ars_id):
    if df_routes.empty: return ""
    route_path = df_routes[df_routes['노선명'] == bus_no].sort_values('순번')
    if route_path.empty: return ""
    current_node = route_path[route_path['ARS_ID'] == current_ars_id]
    if current_node.empty: return ""
    current_seq = current_node.iloc[0]['순번']
    next_node = route_path[route_path['순번'] == current_seq + 1]
    if not next_node.empty:
        return f"👉 {next_node.iloc[0]['정류소명']}방향"
    return "🏁 종점행"


# =================================================================
# 🛠️ Tool 1: 기존 안전빵 (getLowArrInfoByStId)
# =================================================================
def get_station_arrival(keyword: str) -> str:
    # (기존 V21 코드와 동일: ARS/이름 검색 -> 9자리 ID 변환 -> getLow... 호출)
    print(f"[Tool 1] '{keyword}' 검색 (LowFloor API)")
    if df_stations.empty: return "❌ 데이터 없음"
    
    if keyword.isdigit() and len(keyword) <= 5:
        results = df_stations[df_stations['ars_id'] == keyword.zfill(5)]
    else:
        mask = df_stations['정류장명'].str.contains(keyword)
        results = df_stations[mask].head(4)
        
    if results.empty: return f"❌ '{keyword}' 검색 결과가 없습니다."
    
    final_output = f"🚏 **'{keyword}' 도착 정보 (Tool 1)**\n"
    url = "http://ws.bus.go.kr/api/rest/arrive/getLowArrInfoByStId"
    
    for _, row in results.iterrows():
        st_name = row['정류장명']
        api_st_id = row['api_id']
        user_ars_id = row['ars_id']
        final_output += f"\n📍 **{st_name}** ({user_ars_id})"
        
        try:
            params = {"serviceKey": DECODED_KEY, "stId": api_st_id, "resultType": "json"}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if 'msgBody' in data and data['msgBody']['itemList']:
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                count = 0
                for bus in items:
                    rt_nm = bus.get('rtNm', '?')
                    msg1 = bus.get('arrmsg1', '')
                    if msg1 != '운행종료' and msg1 != '출발대기':
                        adirection = bus.get('adirection', '')
                        dir_text = f"👉 {adirection} 방면" if (adirection and adirection != "None") else get_direction_from_csv(rt_nm, user_ars_id)
                        final_output += f"\n   🚌 **{rt_nm}**: {msg1} {dir_text}"
                        count += 1
                if count == 0: final_output += "\n   (도착 예정 버스 없음)"
            else: final_output += "\n   (데이터 없음)"
        except: final_output += "\n   ⚠️ 조회 실패"
    return final_output


# =================================================================
# 🛠️ Tool 2: 버스 위치 (getArrInfoByRouteAll)
# =================================================================
def get_bus_location(bus_number: str) -> str:
    # (기존 V21 코드와 동일)
    print(f"[Tool 2] '{bus_number}'번 위치")
    if df_routes.empty: return "❌ 노선 데이터 없음"
    target_row = df_routes[df_routes['노선명'] == bus_number]
    if target_row.empty: return f"❌ 버스 없음"
    
    route_id = target_row.iloc[0]['ROUTE_ID']
    url = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll"
    params = {"serviceKey": DECODED_KEY, "busRouteId": route_id, "resultType": "json"}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if 'msgBody' not in data: return "⚠️ 데이터 없음"
        items = data['msgBody']['itemList']
        if isinstance(items, dict): items = [items]
        
        output = f"🚍 **[{bus_number}번 버스 위치]**\n"
        bus_count = 0
        for i, item in enumerate(items):
            msg = item.get('arrmsg1', '')
            this_st = item.get('stNm', '')
            if '곧 도착' in msg or '[0번째 전]' in msg:
                next_st = items[i+1].get('stNm') if i+1 < len(items) else "종점"
                output += f"\n🚌 **{bus_count+1}호차**: **{this_st}** (진입) -> {next_st}\n"
                bus_count += 1
            elif '[1번째 전]' in msg:
                prev_st = items[i-1].get('stNm') if i > 0 else "기점"
                output += f"\n🚌 **{bus_count+1}호차**: **{prev_st}** -> {this_st} ({msg})\n"
                bus_count += 1
        if bus_count == 0: output += "\n운행 중인 차량 없음"
        return output
    except Exception as e: return f"❌ 에러: {e}"


# =================================================================
# 🧪 Tool 3: 일반 도착 정보 테스트 (getArrInfoByUid)
# 목적: 9자리 ID 매핑이 적용된 상태에서 이 API가 작동하는지 확인
# =================================================================
def test_general_arrival(keyword: str) -> str:
    print(f"[Tool 3] '{keyword}' 실험 (getArrInfoByUid)")
    if df_stations.empty: return "❌ 데이터 없음"
    
    # 1. 검색 (ARS ID 또는 이름)
    if keyword.isdigit() and len(keyword) <= 5:
        results = df_stations[df_stations['ars_id'] == keyword.zfill(5)]
    else:
        mask = df_stations['정류장명'].str.contains(keyword)
        results = df_stations[mask].head(4)
        
    if results.empty: return f"❌ '{keyword}' 검색 결과가 없습니다."
    
    final_output = f"🧪 **'{keyword}' 실험 결과 (Tool 3: General API)**\n"
    # ⭐ 테스트 대상 API ⭐
    url = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByUid"
    
    for _, row in results.iterrows():
        st_name = row['정류장명']
        api_st_id = row['api_id'] # 9자리 변환된 ID
        user_ars_id = row['ars_id']
        
        final_output += f"\n📍 **{st_name}** ({user_ars_id})"
        final_output += f"\n   ↳ 요청 ID(stId): {api_st_id}" # 디버깅용 출력
        
        try:
            params = {"serviceKey": DECODED_KEY, "stId": api_st_id, "resultType": "json"}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            # API 에러 확인
            if 'msgHeader' in data and data['msgHeader']['headerCd'] != '0':
                err_msg = data['msgHeader']['headerMsg']
                final_output += f"\n   🚫 API 거부: {err_msg}"
                continue

            if 'msgBody' in data and data['msgBody']['itemList']:
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                
                count = 0
                for bus in items:
                    rt_nm = bus.get('rtNm', '?')
                    msg1 = bus.get('arrmsg1', '')
                    # 방향 표시 로직 (Tool 1과 동일)
                    adirection = bus.get('adirection', '')
                    dir_text = f"👉 {adirection}" if (adirection and adirection != "None") else ""
                    
                    if msg1 != '운행종료' and msg1 != '출발대기':
                        final_output += f"\n   ✅ [{rt_nm}] {msg1} {dir_text}"
                        count += 1
                if count == 0: final_output += "\n   (운행 중인 버스 없음)"
            else:
                final_output += "\n   (데이터 리스트 없음 - 권한은 있는데 내용이 빔)"
                
        except Exception as e:
            final_output += f"\n   ⚠️ 시스템 에러: {str(e)}"
            
    return final_output


# -----------------------------------------------------------------
# 🚀 핸들러
# -----------------------------------------------------------------
TOOLS = [
    {"name": "get_station_arrival", "description": "[안전] 정류장 도착 정보 (LowFloor API)", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}, "func": get_station_arrival},
    {"name": "get_bus_location", "description": "[위치] 버스 현재 위치 조회", "inputSchema": {"type": "object", "properties": {"bus_number": {"type": "string"}}, "required": ["bus_number"]}, "func": get_bus_location},
    {"name": "test_general_arrival", "description": "[실험] 정류장 일반 도착 정보 (getArrInfoByUid 테스트)", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}, "func": test_general_arrival}
]

async def handle_request(request):
    if request.method == "GET" or request.method == "HEAD": return JSONResponse({"status": "BusRam V22 Online"})
    try:
        body = await request.json()
        msg_id = body.get("id")
        if body.get("method") == "initialize": 
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "BusRam", "version": "1.1.4"}}})
        elif body.get("method") == "tools/list": 
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]}})
        elif body.get("method") == "tools/call":
            tool = next((t for t in TOOLS if t["name"] == body["params"]["name"]), None)
            if tool:
                res = await run_in_threadpool(tool["func"], **body["params"]["arguments"])
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": res}]}})
    except: pass
    return JSONResponse({"error": "Error"}, status_code=500)

app = Starlette(debug=True, routes=[
    Route("/", endpoint=handle_request, methods=["POST", "GET"]),
    Route("/mcp", endpoint=handle_request, methods=["POST", "GET"])
], middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))