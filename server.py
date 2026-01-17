# =================================================================
# BusRam MCP Server (V18: Pinpoint Location Mode)
# "노선 전체 조회" 데이터를 분석하여 '현재 위치'와 '다음 정류장'만 추출
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

# [1] 데이터 로드
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
    df_stations['clean_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x))
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
# 🛠️ 도구 1: 정류장 도착 정보 (이전 버전 유지)
# =================================================================
def get_station_arrival(keyword: str) -> str:
    print(f"[Tool 1] '{keyword}' 검색")
    if df_stations.empty: return "❌ 서버 에러: 정류장 데이터 없음"
    
    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask].head(4)
    if results.empty: return f"❌ '{keyword}' 검색 결과가 없습니다."
    
    final_output = f"🚏 **'{keyword}' 도착 정보**\n"
    url = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByUid"
    
    for _, row in results.iterrows():
        st_name = row['정류장명']
        ars_raw = row.get('모바일단축번호', '')
        if pd.isna(ars_raw) or not str(ars_raw).strip(): continue
        ars_id = str(int(float(ars_raw))).zfill(5)
        
        final_output += f"\n📍 **{st_name}** ({ars_id})"
        try:
            params = {"serviceKey": DECODED_KEY, "arsId": ars_id, "resultType": "json"}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if 'msgBody' in data and data['msgBody']['itemList']:
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                count = 0
                for bus in items:
                    rt_nm = bus.get('rtNm', '?')
                    msg1 = bus.get('arrmsg1', '정보없음')
                    adirection = bus.get('adirection', '')
                    
                    dir_text = ""
                    if adirection and adirection != "None": dir_text = f"👉 {adirection} 방면"
                    else: dir_text = get_direction_from_csv(rt_nm, ars_id)

                    if msg1 != '운행종료' and msg1 != '출발대기':
                        final_output += f"\n   🚌 **{rt_nm}**: {msg1} {dir_text}"
                        count += 1
                if count == 0: final_output += "\n   (도착 예정 버스 없음)"
            else: final_output += "\n   (도착 정보 없음)"
        except: final_output += "\n   ⚠️ 조회 실패"
    return final_output


# =================================================================
# 🛠️ 도구 2: 버스 위치 조회 (족집게 요약 모드)
# =================================================================
def get_bus_location(bus_number: str) -> str:
    print(f"[Tool 2] '{bus_number}'번 버스 위치 요약")
    
    if df_routes.empty: return "❌ 노선 데이터 없음"
    target_row = df_routes[df_routes['노선명'] == bus_number]
    if target_row.empty: return f"❌ '{bus_number}'번 버스를 찾을 수 없습니다."
    
    route_id = target_row.iloc[0]['ROUTE_ID']
    url = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll"
    params = {"serviceKey": DECODED_KEY, "busRouteId": route_id, "resultType": "json"}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if 'msgBody' not in data: return "⚠️ 데이터 없음"
        items = data['msgBody']['itemList']
        if isinstance(items, dict): items = [items]
        
        output = f"🚍 **[{bus_number}번 버스 실시간 위치]**\n(총 {len(items)}개 정류장 중 운행 차량 추출)\n"
        bus_count = 0
        
        # 리스트를 순회하면서 '버스 위치'를 추정
        for i, item in enumerate(items):
            msg = item.get('arrmsg1', '')
            this_station = item.get('stNm', '')
            
            # 🎯 [핵심 로직] 
            # 1. "곧 도착" -> 버스가 현재 정류장(this_station)에 있음
            # 2. "[1번째 전]" -> 버스가 바로 전 정류장(prev_station)에 있음
            
            if '곧 도착' in msg or '[0번째 전]' in msg:
                # 버스가 '현재 정류장'에 진입 중
                next_station_name = items[i+1].get('stNm') if i+1 < len(items) else "종점"
                
                output += f"\n🚌 **{bus_count+1}호차**\n"
                output += f"   📍 현재: **{this_station}** (진입 중)\n"
                output += f"   👉 다음: {next_station_name}\n"
                bus_count += 1
                
            elif '[1번째 전]' in msg:
                # 버스가 '이전 정류장'을 떠나 '현재 정류장'으로 오는 중
                prev_station_name = items[i-1].get('stNm') if i > 0 else "기점"
                
                output += f"\n🚌 **{bus_count+1}호차**\n"
                output += f"   📍 현재: **{prev_station_name}**\n"
                output += f"   👉 다음: {this_station} ({msg})\n"
                bus_count += 1
        
        if bus_count == 0: 
            output += "\nCurrently, no buses are running or data is unavailable."
            
        return output
        
    except Exception as e: return f"❌ 에러 발생: {e}"


# -----------------------------------------------------------------
# 🚀 핸들러
# -----------------------------------------------------------------
TOOLS = [
    {
        "name": "get_station_arrival", 
        "description": "정류장 이름을 검색하여 버스 도착 정보를 조회합니다.", 
        "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}, 
        "func": get_station_arrival
    },
    {
        "name": "get_bus_location", 
        "description": "버스 번호를 입력받아 현재 버스의 위치(현재역->다음역)를 간단히 조회합니다.", 
        "inputSchema": {"type": "object", "properties": {"bus_number": {"type": "string"}}, "required": ["bus_number"]}, 
        "func": get_bus_location
    }
]

async def handle_request(request):
    if request.method == "GET": return JSONResponse({"status": "BusRam V18 Online"})
    try:
        body = await request.json()
        msg_id = body.get("id")
        
        if body.get("method") == "initialize": 
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "BusRam", "version": "1.1.0"}}})
        elif body.get("method") == "tools/list": 
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]}})
        elif body.get("method") == "tools/call":
            tool_name = body["params"]["name"]
            tool = next((t for t in TOOLS if t["name"] == tool_name), None)
            if tool:
                res = await run_in_threadpool(tool["func"], **body["params"]["arguments"])
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": res}]}})
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})
    except: pass
    return JSONResponse({"error": "Error"}, status_code=500)

app = Starlette(debug=True, routes=[
    Route("/", endpoint=handle_request, methods=["POST", "GET"]),
    Route("/mcp", endpoint=handle_request, methods=["POST", "GET"])
], middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))