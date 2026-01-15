# =================================================================
# BusRam MCP Server (V12: Protocol Version Update)
# =================================================================
import uvicorn
import requests
import pandas as pd
import os
import json
import re
import math
from urllib.parse import unquote
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

# 1. 설정
ENCODING_KEY = os.environ.get("ENCODING_KEY", "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D")
DECODED_KEY = unquote(ENCODING_KEY)

print("📂 [System] 데이터 로딩 시작...")
STATION_CSV = "station_data.csv"
ROUTE_CSV = "route_data.csv"

# [1] 정류장 로드
try:
    try: df_stations = pd.read_csv(STATION_CSV, encoding='cp949')
    except: df_stations = pd.read_csv(STATION_CSV, encoding='utf-8')
    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    df_stations['clean_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x))
    print(f"✅ [Stations] 정류장 로드 완료.")
except: df_stations = pd.DataFrame()

# [2] 노선 로드
try:
    df_routes = pd.read_csv(ROUTE_CSV, encoding='utf-8')
    df_routes['노선명'] = df_routes['노선명'].astype(str)
    df_routes['ROUTE_ID'] = df_routes['ROUTE_ID'].astype(str)
    df_routes['ARS_ID'] = df_routes['ARS_ID'].astype(str).apply(lambda x: x.split('.')[0].zfill(5))
    df_routes['순번'] = pd.to_numeric(df_routes['순번'], errors='coerce').fillna(0).astype(int)
    print(f"✅ [Routes] 노선 로드 완료.")
except: df_routes = pd.DataFrame()

# --- 분석 함수 ---
def calculate_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    d_lon = lon2 - lon1
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(d_lon))
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def get_cardinal_direction(bearing):
    return ['북(N)', '북동(NE)', '동(E)', '남동(SE)', '남(S)', '남서(SW)', '서(W)', '북서(NW)'][round(bearing / 45) % 8]

def get_direction_from_csv(bus_no, current_ars_id):
    if df_routes.empty: return ""
    route_path = df_routes[df_routes['노선명'] == bus_no].sort_values('순번')
    if route_path.empty: return ""
    current_node = route_path[route_path['ARS_ID'] == current_ars_id]
    if current_node.empty: return ""
    current_seq = current_node.iloc[0]['순번']
    next_node = route_path[route_path['순번'] == current_seq + 1]
    if not next_node.empty:
        return f"👉 {next_node.iloc[0]['정류소명']}방향 ({route_path.iloc[-1]['정류소명']}행)"
    return "🏁 종점 부근"

# --- Tool 1: 정류장 도착 정보 ---
def get_bus_arrival(keyword: str) -> str:
    print(f"[Tool 1] '{keyword}' 정류장 검색")
    if df_stations.empty: return "❌ 데이터 로드 실패"
    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask].head(4)
    if results.empty: return f"❌ '{keyword}' 정류장을 찾을 수 없습니다."
    
    final_output = f"🚏 '{keyword}' 정류장 도착 정보:\n"
    url = "http://ws.bus.go.kr/api/rest/arrive/getLowArrInfoByStId"
    
    for _, row in results.iterrows():
        st_name = row['정류장명']
        raw_id = row['정류장번호']
        st_id = re.sub(r'[^0-9]', '', str(raw_id))
        ars_raw = row.get('모바일단축번호', '')
        clean_ars = str(int(float(ars_raw))).zfill(5) if pd.notnull(ars_raw) and str(ars_raw).strip() else ""
        
        final_output += f"\n📍 {st_name} (ARS: {clean_ars}) [서울]"
        
        try:
            params = {"serviceKey": DECODED_KEY, "stId": st_id, "resultType": "json"}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if 'msgBody' not in data or not data['msgBody']['itemList']:
                final_output += "\n   💤 도착 예정 버스 없음"
                continue
                
            items = data['msgBody']['itemList']
            if isinstance(items, dict): items = [items]
            
            for bus in items:
                rt_nm = bus.get('rtNm')
                msg1 = bus.get('arrmsg1')
                adirection = bus.get('adirection', '')
                
                dir_text = ""
                if adirection and adirection != "None": dir_text = f"👉 {adirection} 방면"
                else: dir_text = get_direction_from_csv(rt_nm, clean_ars)
                
                final_output += f"\n   🚌 [{rt_nm}] {msg1}  {dir_text}"
        except Exception as e:
            final_output += f"\n   - (조회 실패)"
    return final_output

# --- Tool 2: 노선 브리핑 ---
def get_bus_route_info(bus_number: str) -> str:
    print(f"[Tool 2] '{bus_number}'번 버스 검색")
    if df_routes.empty: return "❌ 노선 데이터 로드 실패"
    
    clean_no = re.sub(r'[^0-9-]', '', bus_number) 
    target_route = df_routes[df_routes['노선명'] == clean_no]
    
    if target_route.empty: return f"❌ '{bus_number}'번 버스 데이터 없음"
    
    route_id = target_route.iloc[0]['ROUTE_ID']
    url = "http://ws.bus.go.kr/api/rest/buspos/getBusPosByRtid"
    params = {"serviceKey": DECODED_KEY, "busRouteId": route_id, "resultType": "json"}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if 'msgBody' not in data or not data['msgBody']['itemList']: return f"💤 운행 중인 버스 없음"
             
        items = data['msgBody']['itemList']
        if isinstance(items, dict): items = [items]
        
        report = f"🚍 **[{clean_no}번 버스 현황]** (총 {len(items)}대)\n"
        
        for i, bus in enumerate(items):
            sect_ord = bus.get('sectOrd', '?')
            congetion = bus.get('congetion', '0')
            status = "🟢여유" if congetion != '3' else "🟡혼잡"
            
            st_name = f"구간({sect_ord})"
            try:
                match_row = target_route[target_route['순번'] == int(sect_ord)]
                if not match_row.empty: st_name = match_row.iloc[0]['정류소명']
            except: pass

            report += f"{i+1}. {st_name} 부근 ({status})\n"
        return report
    except Exception as e: return f"❌ API 조회 실패: {str(e)}"

# -----------------------------------------------------------------
# 🚀 통합 핸들러 (GET/POST 모두 처리)
# -----------------------------------------------------------------
TOOLS = [
    {"name": "get_bus_arrival", "description": "특정 정류장의 버스 도착 정보를 조회합니다. (예: 서울역 버스)", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}, "func": get_bus_arrival},
    {"name": "get_bus_route_info", "description": "특정 버스 노선의 현재 위치와 운행 대수를 조회합니다. (예: 7016번 버스 위치)", "inputSchema": {"type": "object", "properties": {"bus_number": {"type": "string"}}, "required": ["bus_number"]}, "func": get_bus_route_info}
]

async def handle_request(request):
    # 1. GET 요청 (UptimeRobot, 브라우저 접속용) -> 헬스체크 응답
    if request.method == "GET":
        return JSONResponse({
            "status": "BusRam MCP Online",
            "version": "1.0.1",
            "description": "Bus Arrival & Route Info MCP Server"
        })

    # 2. POST 요청 (Kakao MCP 통신용)
    try:
        body = await request.json()
        method = body.get("method")
        msg_id = body.get("id")

        if method == "initialize": 
            return JSONResponse({
                "jsonrpc": "2.0", 
                "id": msg_id, 
                "result": {
                    # 🟢 [수정] 가이드 문서에서 요구하는 최신 스펙 버전으로 변경
                    "protocolVersion": "2025-03-26", 
                    "capabilities": {
                        "tools": {},
                        # 🟢 [추가] 빈 객체라도 명시해주는 것이 표준 스펙 준수에 유리함
                        "resources": {},
                        "prompts": {}
                    },
                    "serverInfo": {
                        "name": "BusRam",
                        "version": "1.0.2" # 서버 버전도 살짝 올림
                    }
                }
            })
        elif method == "tools/list": 
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id, 
                "result": {"tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]}
            })
        elif method == "tools/call":
            params = body.get("params", {}); tool_name = params.get("name"); args = params.get("arguments", {})
            tool = next((t for t in TOOLS if t["name"] == tool_name), None)
            if tool:
                result_text = await run_in_threadpool(tool["func"], **args)
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": result_text}], "isError": False}})
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})
        
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})
    except Exception as e: 
        return JSONResponse({"error": str(e)}, status_code=500)

app = Starlette(debug=True, routes=[
    Route("/", endpoint=handle_request, methods=["POST", "GET"]),
    Route("/mcp", endpoint=handle_request, methods=["POST", "GET"])
], middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)