# =================================================================
# BusRam MCP Server (V9 Final: Route Analysis & Key Fix)
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

# 1. 설정 (사용자님의 인코딩된 키)
ENCODING_KEY = os.environ.get("ENCODING_KEY", "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D")

# 🟢 [핵심 1] 키 디코딩 (HTML 에러 방지용)
# requests 라이브러리는 전송 시 자동으로 인코딩을 하므로, 우리는 '풀어서(Decode)' 줘야 합니다.
DECODED_KEY = unquote(ENCODING_KEY)

print("📂 [System] 데이터 로딩 시작...")
STATION_CSV = "station_data.csv"
ROUTE_CSV = "route_data.csv"

# -----------------------------------------------------------------
# 📂 데이터 로드
# -----------------------------------------------------------------

# 1) 정류장 데이터 (위치 찾기용)
try:
    try: df_stations = pd.read_csv(STATION_CSV, encoding='cp949')
    except: df_stations = pd.read_csv(STATION_CSV, encoding='utf-8')
    
    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    df_stations['도시코드'] = df_stations['도시코드'].astype(str)
    # 정류장번호(stId) 정제: 숫자만 남김
    df_stations['clean_id'] = df_stations['정류장번호'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
    
    print(f"✅ [Stations] {len(df_stations)}개 정류장 로드 완료.")
except Exception as e:
    print(f"❌ [Stations] 로드 실패: {e}")
    df_stations = pd.DataFrame()

# 2) 노선 데이터 (방면 찾기용 - 치트키!)
try:
    df_routes = pd.read_csv(ROUTE_CSV, encoding='utf-8')
    
    # 데이터 타입 안전하게 변환
    df_routes['노선명'] = df_routes['노선명'].astype(str)
    # NODE_ID(stId) 정제: 숫자만 남김 (매칭용)
    df_routes['clean_node_id'] = df_routes['NODE_ID'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
    # 순번 정수화
    df_routes['순번'] = pd.to_numeric(df_routes['순번'], errors='coerce').fillna(0).astype(int)
    
    print(f"✅ [Routes] {len(df_routes)}개 노선 정보 로드 완료.")
except Exception as e:
    print(f"❌ [Routes] 로드 실패: {e}")
    df_routes = pd.DataFrame()


# -----------------------------------------------------------------
# 🧮 분석 함수 (CSV에서 방면 찾기)
# -----------------------------------------------------------------
def get_direction_from_csv(bus_no, current_st_id):
    """
    CSV 노선도를 뒤져서 '다음 정류장'을 찾아내는 함수
    """
    if df_routes.empty: return ""
    
    # 1. 해당 버스 노선만 필터링 (순번대로 정렬)
    # 예: '150'번 버스의 전체 경로 가져오기
    route_path = df_routes[df_routes['노선명'] == bus_no].sort_values('순번')
    
    if route_path.empty: return ""

    # 2. 현재 정류장(stId)이 이 노선의 몇 번째 순서인지 찾기
    current_node = route_path[route_path['clean_node_id'] == current_st_id]
    
    if current_node.empty: return ""
    
    # (첫 번째 매칭되는 순번 사용 - 순환 노선 등은 약식 처리)
    current_seq = current_node.iloc[0]['순번']
    
    # 3. 바로 다음 정류장 (순번 + 1) 찾기
    next_node = route_path[route_path['순번'] == current_seq + 1]
    
    if not next_node.empty:
        next_name = next_node.iloc[0]['정류소명']
        # 기왕이면 종점(마지막 정류장) 이름도 가져오기
        final_dest = route_path.iloc[-1]['정류소명']
        
        return f"👉 {next_name}방향 ({final_dest}행)"
    else:
        return "🏁 종점 부근"


# -----------------------------------------------------------------
# 🛠️ Main Tool
# -----------------------------------------------------------------
def get_bus_arrival(keyword: str) -> str:
    print(f"[Tool] '{keyword}' 요청")
    
    if df_stations.empty: return "❌ 서버 에러: 데이터 로드 실패"

    # 키워드 검색
    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask]
    
    if results.empty: return f"❌ '{keyword}' 검색 결과가 없습니다."
    
    targets = results.head(4)
    final_output = f"🚏 '{keyword}' 분석 리포트 (V9):"
    
    # API 주소 (stId 기반 조회 - 가장 안정적)
    url_seoul = "http://ws.bus.go.kr/api/rest/arrive/getLowArrInfoByStId"
    
    for _, row in targets.iterrows():
        station_name = row['정류장명']
        city_code = row['도시코드']
        raw_id = row['정류장번호'] 
        
        # ARS 번호 (화면 표시용)
        ars_raw = row.get('모바일단축번호', '')
        ars_display = ""
        try:
            if pd.notnull(ars_raw) and str(ars_raw).strip() != "":
                ars_display = f"(ARS: {str(int(float(ars_raw))).zfill(5)})"
        except: pass
        
        # ID 정제
        station_id = re.sub(r'[^0-9]', '', str(raw_id))
        
        # ---------------------------------------------------------
        # [Case 1] 서울 (API + CSV 노선 분석)
        # ---------------------------------------------------------
        if city_code == '11':
            final_output += f"\n\n📍 {station_name} {ars_display} [서울]"
            
            # 🟢 [핵심 2] Decoded Key 사용 (params가 다시 인코딩해줌)
            params = {
                "serviceKey": DECODED_KEY, 
                "stId": station_id, 
                "resultType": "json"
            }
            
            try:
                response = requests.get(url_seoul, params=params, timeout=5)
                
                # XML 에러 방어
                try: data = response.json()
                except: 
                    # HTML이 오면 키 문제일 확률 99%
                    final_output += f"\n   ⚠️ API 키 에러 발생. 원본: {response.text[:50]}..."
                    continue

                if 'msgHeader' in data and data['msgHeader']['headerCd'] != '0':
                     err_msg = data['msgHeader'].get('headerMsg', '에러')
                     final_output += f"\n   - (API 메시지: {err_msg})"
                     continue

                if 'msgBody' not in data or not data['msgBody']['itemList']:
                    final_output += "\n   💤 도착 예정 버스 없음"
                    continue
                
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                
                for bus in items:
                    rt_nm = bus.get('rtNm')       # 버스 번호
                    msg1 = bus.get('arrmsg1')     # 도착 예정 시간
                    
                    # 🟢 [핵심 3] 방면 찾기 (API가 안 주면 CSV에서 찾는다!)
                    adirection = bus.get('adirection', '') 
                    
                    dir_text = ""
                    if adirection and adirection != "None":
                        dir_text = f"👉 {adirection} 방면"
                    else:
                        # API가 모르면 우리가 만든 족보(CSV) 검색
                        csv_dir = get_direction_from_csv(rt_nm, station_id)
                        if csv_dir:
                            dir_text = csv_dir

                    bus_info = f"\n   🚌 [{rt_nm}] {msg1}"
                    if dir_text:
                        bus_info += f"  {dir_text}"
                        
                    final_output += bus_info

            except Exception as e:
                final_output += f"\n   - (통신 에러: {str(e)})"

        # [Case 2] 경기 (기존 유지)
        elif city_code.startswith('31') or city_code == '12': 
            final_output += f"\n\n📍 {station_name} {ars_display} [경기]"
            # 경기 API URL
            url_gyeonggi = "http://apis.data.go.kr/6410000/busarrivalservice/getBusArrivalList"
            params = {"serviceKey": DECODED_KEY, "stationId": station_id}
            try:
                response = requests.get(url_gyeonggi, params=params, timeout=5)
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

        # [Case 3] 전국 (기존 유지)
        if "[서울]" not in final_output and "[경기]" not in final_output:
            if "📍" not in final_output: 
                final_output += f"\n\n📍 {station_name} {ars_display} [전국]"
            
            url_nat = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList"
            params = {
                "serviceKey": DECODED_KEY, 
                "cityCode": city_code, 
                "nodeId": station_id, 
                "numOfRows": 5, 
                "_type": "json"
            }
            try:
                response = requests.get(url_nat, params=params, timeout=5)
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

# 실행부
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