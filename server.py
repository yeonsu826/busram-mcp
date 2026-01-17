# =================================================================
# BusRam MCP Server (V23: Final Stable Version)
# - Tool 1: getLowArrInfoByStId (ID 변환 기능 탑재로 완벽 지원)
# - Tool 2: getArrInfoByRouteAll (버스 위치 족집게)
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
import xml.etree.ElementTree as ET

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
    df_routes['ARS_ID'] = df_routes['ARS_ID'].astype(str).apply(lambda x: x.split('.')[0].zfill(5))
except: df_routes = pd.DataFrame()

try:
    try: df_stations = pd.read_csv(STATION_CSV, encoding='cp949')
    except: df_stations = pd.read_csv(STATION_CSV, encoding='utf-8')
    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    
    # 1. API용 9자리 ID
    if '정류소ID' in df_stations.columns:
        df_stations['api_id'] = df_stations['정류소ID'].astype(str)
    elif 'NODE_ID' in df_stations.columns:
        df_stations['api_id'] = df_stations['NODE_ID'].astype(str)
    else:
        df_stations['api_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x))

    # 2. 사용자용 5자리 ARS ID
    if '모바일단축번호' in df_stations.columns:
        df_stations['ars_id'] = df_stations['모바일단축번호'].fillna(0).astype(str).apply(lambda x: x.split('.')[0].zfill(5))
    else:
        df_stations['ars_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x)[-5:].zfill(5))
        
    print(f"✅ 데이터 로드 완료: {len(df_stations)}개 정류장")
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
# 🛠️ Tool 1: 정류장 도착 정보 (ID 변환 + 안전 파싱)
# =================================================================
def get_station_arrival(keyword: str) -> str:
    print(f"[Tool 1] '{keyword}' 검색")
    if df_stations.empty: return "❌ 데이터 없음"
    
    # 1. 검색 (ARS ID 우선, 없으면 이름)
    if keyword.isdigit() and len(keyword) <= 5:
        results = df_stations[df_stations['ars_id'] == keyword.zfill(5)]
    else:
        mask = df_stations['정류장명'].str.contains(keyword)
        results = df_stations[mask].head(4)
        
    if results.empty: return f"❌ '{keyword}' 검색 결과가 없습니다."
    
    final_output = f"🚏 **'{keyword}' 도착 정보**\n"
    # 문서 3번 API (유일한 희망)
    url = "http://ws.bus.go.kr/api/rest/arrive/getLowArrInfoByStId"
    
    for _, row in results.iterrows():
        st_name = row['정류장명']
        api_st_id = row['api_id'] # 9자리
        user_ars_id = row['ars_id'] # 5자리
        
        final_output += f"\n📍 **{st_name}** ({user_ars_id})"
        
        try:
            params = {"serviceKey": DECODED_KEY, "stId": api_st_id, "resultType": "json"}
            response = requests.get(url, params=params, timeout=5)
            
            # 🚨 JSON 파싱 시도 (실패 시 XML/Text 확인)
            try:
                data = response.json()
            except json.JSONDecodeError:
                # JSON이 아니면 에러 메시지일 확률 높음
                final_output += f"\n   ⚠️ 서버 응답 오류 (XML/HTML 반환됨)"
                continue

            if 'msgHeader' in data and data['msgHeader']['headerCd'] != '0':
                final_output += f"\n   (정보 없음)"
                continue

            if 'msgBody' in data and data['msgBody']['itemList']:
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                
                count = 0
                for bus in items:
                    rt_nm = bus.get('rtNm', '?')
                    msg1 = bus.get('arrmsg1', '')
                    adirection = bus.get('adirection', '')
                    
                    dir_text = ""
                    if adirection and adirection != "None": dir_text = f"👉 {adirection} 방면"
                    else: dir_text = get_direction_from_csv(rt_nm, user_ars_id)

                    if msg1 != '운행종료' and msg1 != '출발대기':
                        final_output += f"\n   🚌 **{rt_nm}**: {msg1} {dir_text}"
                        count += 1
                
                if count == 0: final_output += "\n   (도착 예정 버스 없음)"
            else:
                final_output += "\n   (도착 정보 없음)"
                
        except Exception as e:
            final_output += f"\n   ⚠️ 에러: {str(e)}"
            
    return final_output


# =================================================================
# 🛠️ Tool 2: 버스 위치 조회 (성공작 유지)
# =================================================================
def get_bus_location(bus_number: str) -> str:
    print(f"[Tool 2] '{bus_number}'번 위치")
    if df_routes.empty: return "❌ 노선 데이터 없음"
    target_row = df_routes[df_routes['노선명'] == bus_number]
    if target_row.empty: return f"❌ '{bus_number}'번 버스를 찾을 수 없습니다."
    
    route_id = target_row.iloc[0]['ROUTE_ID']
    url = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll"
    params = {"serviceKey": DECODED_KEY, "busRouteId": route_id, "resultType": "json"}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json() # 얘는 잘 되니까 걱정 없음
        
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


# -----------------------------------------------------------------
# 🚀 핸들러
# -----------------------------------------------------------------
TOOLS = [
    {
        "name": "get_station_arrival", 
        "description": "정류장 이름(예: 하림각) 또는 ARS-ID(예: 01136)를 입력하여 버스 도착 정보를 조회합니다.", 
        "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}, 
        "func": get_station_arrival
    },
    {
        "name": "get_bus_location", 
        "description": "버스 번호를 입력받아 현재 버스의 위치를 조회합니다.", 
        "inputSchema": {"type": "object", "properties": {"bus_number": {"type": "string"}}, "required": ["bus_number"]}, 
        "func": get_bus_location
    }
]

async def handle_request(request):
    if request.method == "GET" or request.method == "HEAD": return JSONResponse({"status": "BusRam V23 Final Online"})
    try:
        body = await request.json()
        msg_id = body.get("id")
        if body.get("method") == "initialize": 
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "BusRam", "version": "1.2.0"}}})
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