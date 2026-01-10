# =================================================================
# BusRam MCP Server (V6: Deep Debugging Mode)
# =================================================================
import uvicorn
import requests
import pandas as pd
import os
import json
import re
import math
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

# 1. 설정
ENCODING_KEY = os.environ.get("ENCODING_KEY", "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D")
STATION_CSV = "station_data.csv"
ROUTE_CSV = "route_data.csv"

print("📂 [System] 데이터 로딩 시작...")

# 정류장 로드
try:
    try: df_stations = pd.read_csv(STATION_CSV, encoding='cp949')
    except: df_stations = pd.read_csv(STATION_CSV, encoding='utf-8')
    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    df_stations['도시코드'] = df_stations['도시코드'].astype(str)
    df_stations['정류장번호'] = df_stations['정류장번호'].astype(str)
    df_stations['clean_id'] = df_stations['정류장번호'].apply(lambda x: re.sub(r'[^0-9]', '', x))
    print(f"✅ [Stations] {len(df_stations)}개 로드 완료.")
except Exception as e:
    print(f"❌ [Stations] 로드 실패: {e}")
    df_stations = pd.DataFrame()

# 노선 로드
try:
    df_routes = pd.read_csv(ROUTE_CSV, encoding='utf-8')
    df_routes['노선명'] = df_routes['노선명'].astype(str)
    df_routes['ARS_ID'] = df_routes['ARS_ID'].astype(str).apply(lambda x: x.split('.')[0].zfill(5))
    df_routes['순번'] = pd.to_numeric(df_routes['순번'], errors='coerce').fillna(0).astype(int)
    print(f"✅ [Routes] {len(df_routes)}개 구간 로드 완료.")
    # 디버깅: 노선 데이터 샘플 출력
    print(f"🔍 [DEBUG] 노선 데이터 샘플: {df_routes.head(1).to_dict('records')}")
except Exception as e:
    print(f"❌ [Routes] 로드 실패: {e}")
    df_routes = pd.DataFrame()

# 2. 분석 함수
def calculate_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    d_lon = lon2 - lon1
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(d_lon))
    initial_bearing = math.atan2(y, x)
    return (math.degrees(initial_bearing) + 360) % 360

def get_cardinal_direction(bearing):
    directions = ['북(N)', '북동(NE)', '동(E)', '남동(SE)', '남(S)', '남서(SW)', '서(W)', '북서(NW)']
    return directions[round(bearing / 45) % 8]

def get_direction_from_csv(bus_no, current_ars_id):
    if df_routes.empty: 
        print("🔍 [DEBUG] 노선 DF가 비어있음")
        return ""
    
    # 디버깅: 매칭 시도 로그
    print(f"🔍 [CSV검색] 버스[{bus_no}] / ARS[{current_ars_id}] 찾는 중...")
    
    route_path = df_routes[df_routes['노선명'] == bus_no].sort_values('순번')
    if route_path.empty: 
        print(f"🔍 [CSV실패] 버스[{bus_no}] 데이터 없음. (샘플: {df_routes['노선명'].iloc[0]})")
        return ""

    current_node = route_path[route_path['ARS_ID'] == current_ars_id]
    if current_node.empty: 
        print(f"🔍 [CSV실패] 버스[{bus_no}] 경로는 있는데 정류장[{current_ars_id}]이 그 안에 없음.")
        return ""
    
    current_seq = current_node.iloc[0]['순번']
    next_node = route_path[route_path['순번'] == current_seq + 1]
    
    if not next_node.empty:
        next_name = next_node.iloc[0]['정류소명']
        final_dest = route_path.iloc[-1]['정류소명']
        print(f"🔍 [CSV성공] 다음 정류장: {next_name}")
        return f"👉 {next_name} 쪽 ({final_dest} 방면)"
    else:
        return "🏁 종점/차고지 부근"

# 3. 메인 도구
def get_bus_arrival(keyword: str) -> str:
    print(f"[Tool] '{keyword}' 요청")
    if df_stations.empty: return "❌ DB 로드 실패"

    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask]
    if results.empty: return f"❌ 결과 없음"
    
    targets = results.head(4)
    final_output = f"🚏 '{keyword}' 분석 리포트 (V6 Debug):"
    
    # 🟢 [중요] 키가 고쳐졌으므로 가장 정확한 'ARS ID 조회' API를 다시 사용합니다.
    # 이 API는 'adirection'을 잘 줍니다. CSV는 백업용으로 씁니다.
    url_seoul = "http://ws.bus.go.kr/api/rest/arrive/getStationByUidItem"
    url_gyeonggi = "http://apis.data.go.kr/6410000/busarrivalservice/getBusArrivalList"
    
    for _, row in targets.iterrows():
        station_name = row['정류장명']
        city_code = row['도시코드']
        raw_id = row['정류장번호'] 
        current_lat = row['위도']
        current_lng = row['경도']
        
        ars_raw = row.get('모바일단축번호', '')
        clean_arsId = ""
        try:
            if pd.notnull(ars_raw) and str(ars_raw).strip() != "":
                clean_arsId = str(int(float(ars_raw))).zfill(5)
        except: pass
        
        ars_display = f"(ARS: {clean_arsId})" if clean_arsId else ""
        station_id = re.sub(r'[^0-9]', '', raw_id) 
        
        # [Case 1] 서울
        if city_code == '11':
            final_output += f"\n\n📍 {station_name} {ars_display} [서울]"
            
            if not clean_arsId:
                final_output += "\n   ⚠️ ARS 번호 없음 (조회 불가)"
                continue

            params = {"serviceKey": ENCODING_KEY, "arsId": clean_arsId, "resultType": "json"}
            
            try:
                # 🟢 requests가 자동으로 인코딩 처리를 하도록 params에 딕셔너리로 넘깁니다.
                response = requests.get(url_seoul, params=params, timeout=5)
                
                try: data = response.json()
                except: 
                    # XML 에러가 나면 내용을 보여줌
                    final_output += f"\n   ⚠️ API 키/포맷 에러. 원본: {response.text[:100]}"
                    continue

                if 'msgHeader' in data and data['msgHeader']['headerCd'] != '0':
                     err_msg = data['msgHeader'].get('headerMsg', '에러')
                     final_output += f"\n   - (API 메시지: {err_msg})"
                     continue

                if 'msgBody' not in data or not data['msgBody']['itemList']:
                    final_output += "\n   💤 버스 없음"
                    continue
                
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                
                for bus in items:
                    rt_nm = bus.get('rtNm')
                    msg1 = bus.get('arrmsg1')
                    adirection = bus.get('adirection', '') 
                    nxt_st_id = bus.get('nxtStnId', '')
                    
                    # 1. 방면 결정 (API 우선 -> CSV 백업)
                    dir_text = ""
                    if adirection and adirection != "None":
                        dir_text = f"👉 {adirection} 방면"
                    else:
                        # API가 안주면 CSV 검색
                        csv_dir = get_direction_from_csv(rt_nm, clean_arsId)
                        if csv_dir: dir_text = csv_dir

                    # 2. 방위각 (나침반)
                    bearing_text = ""
                    if nxt_st_id and str(nxt_st_id) != "0":
                        next_st_info = df_stations[df_stations['clean_id'] == str(nxt_st_id)]
                        if not next_st_info.empty:
                            nxt_lat = next_st_info.iloc[0]['위도']
                            nxt_lng = next_st_info.iloc[0]['경도']
                            bearing = calculate_bearing(current_lat, current_lng, nxt_lat, nxt_lng)
                            bearing_text = f" (🧭{get_cardinal_direction(bearing)})"
                    
                    bus_info = f"\n   🚌 [{rt_nm}] {msg1}"
                    if dir_text: bus_info += f" ({dir_text}{bearing_text})"
                    elif bearing_text: bus_info += f" {bearing_text}"
                        
                    final_output += bus_info

            except Exception as e:
                final_output += f"\n   - (에러: {str(e)})"

        # [Case 2] 경기
        elif city_code.startswith('31') or city_code == '12': 
            final_output += f"\n\n📍 {station_name} {ars_display} [경기]"
            request_url = f"{url_gyeonggi}?serviceKey={ENCODING_KEY}"
            params = {"stationId": station_id}
            try:
                response = requests.get(request_url, params=params, timeout=5)
                try: 
                    data = response.json()
                    items = data['response']['msgBody']['busArrivalList']
                    if isinstance(items, dict): items = [items]
                    if not items: raise Exception("No Bus")
                    for bus in items:
                        min_left = bus.get('predictTime1')
                        stops = bus.get('locationNo1')
                        final_output += f"\n   🚌 [버스] {min_left}분 후 ({stops}전)"
                except: pass
            except: pass
            if "버스" not in final_output and "[경기]" in final_output: pass 

        # [Case 3] 전국
        if "[서울]" not in final_output and "[경기]" not in final_output:
            if "📍" not in final_output: 
                final_output += f"\n\n📍 {station_name} {ars_display} [전국]"
            request_url = f"https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList?serviceKey={ENCODING_KEY}"
            params = {"cityCode": city_code, "nodeId": station_id, "numOfRows": 5, "_type": "json"}
            try:
                response = requests.get(request_url, params=params, timeout=5)
                data = response.json()
                items = data['response']['body']['items']['item']
                if isinstance(items, dict): items = [items]
                for bus in items:
                    route_no = bus.get('routeno')
                    min_left = int(bus.get('arrtime')) // 60
                    msg = bus.get('arrmsg1', '')
                    final_output += f"\n   🚌 [{route_no}번] {min_left}분 후 ({msg})"
            except:
                if "도착 예정 버스" not in final_output:
                    final_output += "\n   💤 도착 예정 버스 없음"
            
    return final_output

TOOLS = [{"name": "get_bus_arrival", "description": "버스 정보", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}, "func": get_bus_arrival}]
async def handle_mcp_request(request):
    try:
        body = await request.json(); method = body.get("method"); msg_id = body.get("id")
        if method == "initialize": return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "BusRam", "version": "1.0.0"}}})
        elif method == "tools/list": return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]}})
        elif method == "tools/call":
            params = body.get("params", {}); tool_name = params.get("name"); args = params.get("arguments", {})
            tool = next((t for t in TOOLS if t["name"] == tool_name), None)
            if tool:
                result_text = await run_in_threadpool(tool["func"], **args)
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": result_text}], "isError": False}})
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)
async def handle_root(request): return JSONResponse({"status": "ok", "service": "BusRam MCP"})
middleware = [Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]
app = Starlette(debug=True, routes=[Route("/mcp", endpoint=handle_mcp_request, methods=["POST"]), Route("/", endpoint=handle_root, methods=["GET"])], middleware=middleware)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)