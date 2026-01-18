# =================================================================
# BusRam MCP Server (V28: Text Only Version)
# - 모든 이모티콘(🚌, 📍, 👉, 🚏, 🚍) 제거
# - 텍스트 중심의 깔끔한 출력 (호환성 및 심플함 강조)
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

# [키 설정]
DECODED_KEY = "ezGwhdiNnVtd+HvkfiKgr/Z4r+gvfeUIRz/dVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI+/pJFoYr9Ce+TDg=="

print("[System] 데이터 로딩 중...")
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
    
    if '정류소ID' in df_stations.columns:
        df_stations['api_id'] = df_stations['정류소ID'].astype(str)
    elif 'NODE_ID' in df_stations.columns:
        df_stations['api_id'] = df_stations['NODE_ID'].astype(str)
    else:
        df_stations['api_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x))

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
        # [수정] 이모티콘 제거
        return f"{next_node.iloc[0]['정류소명']} 방향"
    return "종점행"


# =================================================================
# Tool 1: 정류장 도착 정보
# =================================================================
def get_station_arrival(keyword: str) -> str:
    print(f"[Tool 1] '{keyword}' 검색")
    if df_stations.empty: return "데이터 없음"
    
    if keyword.isdigit() and len(keyword) <= 5:
        results = df_stations[df_stations['ars_id'] == keyword.zfill(5)]
    else:
        mask = df_stations['정류장명'].str.contains(keyword)
        results = df_stations[mask].head(4)
        
    if results.empty: return f" '{keyword}' 검색 결과가 없습니다."
    
    # [수정] 이모티콘 제거
    final_output = f"**'{keyword}' 도착 정보**\n"
    url = "http://ws.bus.go.kr/api/rest/arrive/getLowArrInfoByStId"
    
    for _, row in results.iterrows():
        st_name = row['정류장명']
        api_st_id = row['api_id']
        user_ars_id = row['ars_id']
        # [수정] 이모티콘 제거
        final_output += f"\n**{st_name}** ({user_ars_id})"
        
        try:
            params = {"serviceKey": DECODED_KEY, "stId": api_st_id, "resultType": "json"}
            response = requests.get(url, params=params, timeout=5)
            
            try: data = response.json()
            except: 
                final_output += f"\n   응답 오류"
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
                    
                    # [수정] 이모티콘 제거
                    dir_text = f"{adirection} 방면" if (adirection and adirection != "None") else get_direction_from_csv(rt_nm, user_ars_id)

                    if msg1 != '운행종료' and msg1 != '출발대기':
                        # [수정] 이모티콘 제거
                        final_output += f"\n   - **{rt_nm}**: {msg1} {dir_text}"
                        count += 1
                if count == 0: final_output += "\n   (도착 예정 버스 없음)"
            else: final_output += "\n   (도착 정보 없음)"
        except Exception as e: final_output += f"\n   에러: {str(e)}"
    return final_output


# =================================================================
# Tool 2: 버스 위치 조회 (텍스트 전용)
# =================================================================
def get_bus_location(bus_number: str) -> str:
    print(f"[Tool 2] '{bus_number}'번 위치")
    if df_routes.empty: return "노선 데이터 없음"
    target_row = df_routes[df_routes['노선명'] == bus_number]
    if target_row.empty: return f"'{bus_number}'번 버스를 찾을 수 없습니다."
    
    route_id = target_row.iloc[0]['ROUTE_ID']
    url = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll"
    params = {"serviceKey": DECODED_KEY, "busRouteId": route_id, "resultType": "json"}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if 'msgBody' not in data: return "데이터 없음"
        items = data['msgBody']['itemList']
        if isinstance(items, dict): items = [items]
        
        # [수정] 이모티콘 제거
        output = f"**[{bus_number}번 버스 위치]**\n"
        
        detected_buses = {}

        for i, item in enumerate(items):
            msg = item.get('arrmsg1', '')
            this_st = item.get('stNm', '') 
            
            if '[1번째 전]' in msg:
                bus_pos_idx = i - 1
                if bus_pos_idx >= 0:
                    prev_st = items[i-1].get('stNm') if i > 0 else "기점"
                    clean_time = msg.split('[')[0].replace("후", "")
                    
                    # [수정] 이모티콘 제거 및 텍스트 정리
                    display_msg = f"**현재 위치:** {prev_st}\n   **다음 정류장:** {this_st} (약 {clean_time} 후 도착 예정)"
                    detected_buses[bus_pos_idx] = display_msg

            elif '곧 도착' in msg or '[0번째 전]' in msg:
                bus_pos_idx = i
                if bus_pos_idx not in detected_buses:
                    next_st = items[i+1].get('stNm') if i+1 < len(items) else "종점"
                    
                    # [수정] 이모티콘 제거 및 텍스트 정리
                    display_msg = f"**현재 위치:** {this_st} (진입 중)\n   **다음 정류장:** {next_st}"
                    detected_buses[bus_pos_idx] = display_msg

        sorted_indices = sorted(detected_buses.keys())
        
        if not sorted_indices:
            output += "\n운행 중인 차량 없음"
        else:
            for idx in sorted_indices:
                output += f"\n[차량]\n{detected_buses[idx]}\n"

        return output
        
    except Exception as e: return f" 에러: {e}"


# -----------------------------------------------------------------
# 핸들러
# -----------------------------------------------------------------
TOOLS = [
    {"name": "get_station_arrival", "description": "정류장 이름/번호로 도착 정보 조회", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}, "func": get_station_arrival},
    {"name": "get_bus_location", "description": "버스 번호로 현재 위치 조회", "inputSchema": {"type": "object", "properties": {"bus_number": {"type": "string"}}, "required": ["bus_number"]}, "func": get_bus_location}
]

async def handle_request(request):
    if request.method == "GET" or request.method == "HEAD": return JSONResponse({"status": "BusRam V28 TextOnly Online"})
    try:
        body = await request.json()
        msg_id = body.get("id")
        if body.get("method") == "initialize": 
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id, 
                "result": {
                    "protocolVersion": "2025-03-26", 
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}, "logging": {}},
                    "serverInfo": {"name": "BusRam", "version": "1.2.5"}
                }
            })
        elif body.get("method") == "tools/list": 
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]}})
        elif body.get("method") == "tools/call":
            tool = next((t for t in TOOLS if t["name"] == body["params"]["name"]), None)
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