# =================================================================
# BusRam MCP Server (V19: Final Stable - Strict Doc Compliance)
# Tool 1: getLowArrInfoByStId (문서 3번 API 사용) - 에러 해결 우선
# Tool 2: getArrInfoByRouteAll (문서 1번 API 사용) - 완벽 작동 중
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

# [1] 데이터 로드 (ID 컬럼 자동 탐지)
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
    
    # [중요] 9자리 정류소 ID 찾기 (API 필수값)
    # CSV에 '정류소ID', 'NODE_ID' 등이 있으면 그걸 쓰고, 없으면 '정류장번호' 사용
    if '정류소ID' in df_stations.columns:
        df_stations['api_id'] = df_stations['정류소ID'].astype(str)
    elif 'NODE_ID' in df_stations.columns:
        df_stations['api_id'] = df_stations['NODE_ID'].astype(str)
    else:
        # 숫자만 남겨서 ID로 사용
        df_stations['api_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x))
        
    # ARS ID (보여주기용 5자리)
    df_stations['disp_id'] = df_stations['정류장번호'].astype(str)
    
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
# 🛠️ 도구 1: 정류장 도착 정보 (문서 3번 API 복귀)
# API: getLowArrInfoByStId (저상버스 조회지만 일반 버스도 일부 나옴)
# =================================================================
def get_station_arrival(keyword: str) -> str:
    print(f"[Tool 1] '{keyword}' 검색")
    if df_stations.empty: return "❌ 서버 에러: 정류장 데이터 없음"
    
    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask].head(4)
    if results.empty: return f"❌ '{keyword}' 검색 결과가 없습니다."
    
    final_output = f"🚏 **'{keyword}' 도착 정보**\n"
    
    # 🚨 [수정] 사용 가능한 유일한 정류장 API (문서 3번)
    url = "http://ws.bus.go.kr/api/rest/arrive/getLowArrInfoByStId"
    
    for _, row in results.iterrows():
        st_name = row['정류장명']
        st_id = row['api_id']  # 9자리 ID (필수)
        disp_id = row['disp_id'] # 보여주기용

        final_output += f"\n📍 **{st_name}** ({disp_id})"
        
        try:
            params = {"serviceKey": DECODED_KEY, "stId": st_id, "resultType": "json"}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            # 에러 메시지가 있는지 확인 (디버깅용)
            if 'msgHeader' in data and data['msgHeader']['headerCd'] != '0':
                err_msg = data['msgHeader']['headerMsg']
                final_output += f"\n   ⚠️ API 에러: {err_msg}"
                continue

            if 'msgBody' in data and data['msgBody']['itemList']:
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                
                count = 0
                for bus in items:
                    rt_nm = bus.get('rtNm', '?')
                    msg1 = bus.get('arrmsg1', '정보없음')
                    
                    # 방향 찾기 (API가 안 주면 CSV에서)
                    adirection = bus.get('adirection', '')
                    dir_text = ""
                    if adirection and adirection != "None": dir_text = f"👉 {adirection} 방면"
                    else: 
                        # ARS ID 5자리 추출 시도
                        clean_ars = re.sub(r'[^0-9]', '', str(disp_id))
                        if len(clean_ars) > 5: clean_ars = clean_ars[-5:] # 뒤 5자리
                        dir_text = get_direction_from_csv(rt_nm, clean_ars)

                    if msg1 != '운행종료' and msg1 != '출발대기':
                        final_output += f"\n   🚌 **{rt_nm}**: {msg1} {dir_text}"
                        count += 1
                
                if count == 0: final_output += "\n   (도착 예정 버스 없음)"
            else:
                final_output += "\n   (도착 정보 없음)"
                
        except Exception as e:
            # 🚨 에러가 나면 정확한 이유를 출력하도록 수정
            final_output += f"\n   ⚠️ 시스템 에러: {str(e)}"
            
    return final_output


# =================================================================
# 🛠️ 도구 2: 버스 위치 조회 (성공한 V18 버전 유지)
# =================================================================
def get_bus_location(bus_number: str) -> str:
    print(f"[Tool 2] '{bus_number}'번 버스 위치 요약")
    
    if df_routes.empty: return "❌ 노선 데이터 없음"
    target_row = df_routes[df_routes['노선명'] == bus_number]
    if target_row.empty: return f"❌ '{bus_number}'번 버스를 찾을 수 없습니다."
    
    route_id = target_row.iloc[0]['ROUTE_ID']
    # 🚨 [성공 비결] 문서 1번 API (getArrInfoByRouteAll)
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
        
        for i, item in enumerate(items):
            msg = item.get('arrmsg1', '')
            this_station = item.get('stNm', '')
            
            if '곧 도착' in msg or '[0번째 전]' in msg:
                next_station_name = items[i+1].get('stNm') if i+1 < len(items) else "종점"
                output += f"\n🚌 **{bus_count+1}호차**\n   📍 현재: **{this_station}** (진입 중)\n   👉 다음: {next_station_name}\n"
                bus_count += 1
            elif '[1번째 전]' in msg:
                prev_station_name = items[i-1].get('stNm') if i > 0 else "기점"
                output += f"\n🚌 **{bus_count+1}호차**\n   📍 현재: **{prev_station_name}**\n   👉 다음: {this_station} ({msg})\n"
                bus_count += 1
        
        if bus_count == 0: output += "\n현재 운행 중인 차량이 없습니다."
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
        "description": "버스 번호를 입력받아 현재 버스의 위치를 조회합니다.", 
        "inputSchema": {"type": "object", "properties": {"bus_number": {"type": "string"}}, "required": ["bus_number"]}, 
        "func": get_bus_location
    }
]

async def handle_request(request):
    if request.method == "GET": return JSONResponse({"status": "BusRam V19 Online"})
    try:
        body = await request.json()
        msg_id = body.get("id")
        if body.get("method") == "initialize": 
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "BusRam", "version": "1.1.1"}}})
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