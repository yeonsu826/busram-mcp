# =================================================================
# BusRam MCP Server (V4 Stable: Revert to stId + Direction Calc)
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

print("📂 [System] 정류장 데이터(CSV) 로딩 중...")
CSV_PATH = "station_data.csv"

try:
    try: df_stations = pd.read_csv(CSV_PATH, encoding='cp949')
    except: df_stations = pd.read_csv(CSV_PATH, encoding='utf-8')

    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    df_stations['도시코드'] = df_stations['도시코드'].astype(str)
    df_stations['정류장번호'] = df_stations['정류장번호'].astype(str)
    
    # 다음 정류장 매칭을 위한 Clean ID (숫자만 남김)
    df_stations['clean_id'] = df_stations['정류장번호'].apply(lambda x: re.sub(r'[^0-9]', '', x))
    
    print(f"✅ [System] 데이터 로드 완료! 총 {len(df_stations)}개 정류장 대기.")

except Exception as e:
    print(f"❌ [Critical] CSV 파일 로드 실패: {e}")
    df_stations = pd.DataFrame()

# 2. 방위각 계산 함수 (유지)
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

# 3. 메인 도구 함수
def get_bus_arrival(keyword: str) -> str:
    print(f"[Tool] '{keyword}' 검색 시작")
    if df_stations.empty: return "❌ CSV 로드 실패"

    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask]
    if results.empty: return f"❌ '{keyword}' 검색 결과 없음"
    
    targets = results.head(4)
    final_output = f"🚏 '{keyword}' 분석 리포트 (V4 Stable):"
    
    # 🟢 [복구] 원래 쓰시던 '저상버스 조회' API로 돌아왔습니다. (Station ID 사용)
    url_seoul = "http://ws.bus.go.kr/api/rest/arrive/getLowArrInfoByStId"
    url_gyeonggi = "http://apis.data.go.kr/6410000/busarrivalservice/getBusArrivalList"
    url_national = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList"
    
    for _, row in targets.iterrows():
        station_name = row['정류장명']
        city_code = row['도시코드']
        raw_id = row['정류장번호'] 
        current_lat = row['위도']
        current_lng = row['경도']
        
        ars_raw = row.get('모바일단축번호', '')
        ars_display = ""
        try:
            if pd.notnull(ars_raw) and str(ars_raw).strip() != "":
                ars_display = f"(ARS: {str(int(float(ars_raw))).zfill(5)})"
        except: pass

        # CSV의 '정류장번호'에서 숫자만 추출 -> API의 stId로 사용
        station_id = re.sub(r'[^0-9]', '', raw_id) 
        
        # ---------------------------------------------------------
        # [Case 1] 서울 (Station ID 사용 + 방위각 계산)
        # ---------------------------------------------------------
        if city_code == '11':
            final_output += f"\n\n📍 {station_name} {ars_display} [서울]"
            
            # 원래 방식대로 stId 파라미터 사용
            request_url = f"{url_seoul}?serviceKey={ENCODING_KEY}"
            params = {"stId": station_id, "resultType": "json"}
            
            try:
                response = requests.get(request_url, params=params, timeout=5)
                
                # 에러 디버깅을 위한 안전장치
                try:
                    data = response.json()
                except:
                    final_output += "\n   ⚠️ API 응답 오류 (XML 리턴됨)"
                    continue

                if 'msgHeader' in data and data['msgHeader']['headerCd'] != '0':
                     err_msg = data['msgHeader'].get('headerMsg', '알 수 없는 에러')
                     final_output += f"\n   - (API 메시지: {err_msg})"
                     continue

                if 'msgBody' not in data or not data['msgBody']['itemList']:
                    final_output += "\n   💤 도착 예정 버스 없음"
                    continue
                
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                
                for bus in items:
                    rt_nm = bus.get('rtNm')
                    msg1 = bus.get('arrmsg1')
                    adirection = bus.get('adirection', '') # 이 API는 이게 비어있을 수 있음
                    nxt_st_id = bus.get('nxtStnId', '')    # 하지만 이건 줌!
                    
                    # --- [핵심] 방위각 계산 로직 ---
                    direction_str = ""
                    if nxt_st_id and str(nxt_st_id) != "0":
                        # CSV에서 다음 정류장 찾기
                        next_st_info = df_stations[df_stations['clean_id'] == str(nxt_st_id)]
                        if not next_st_info.empty:
                            nxt_lat = next_st_info.iloc[0]['위도']
                            nxt_lng = next_st_info.iloc[0]['경도']
                            
                            # 좌표로 방향 계산
                            bearing = calculate_bearing(current_lat, current_lng, nxt_lat, nxt_lng)
                            cardinal = get_cardinal_direction(bearing)
                            direction_str = f" 🧭{cardinal}쪽"
                    
                    bus_info = f"\n   🚌 [{rt_nm}] {msg1}"
                    
                    # 방면 텍스트가 있으면 쓰고, 없으면 계산된 방향만이라도 보여줌
                    if adirection:
                        bus_info += f" (👉 {adirection} 방면{direction_str})"
                    elif direction_str:
                        bus_info += f" ({direction_str}으로 이동)"
                    
                    final_output += bus_info

            except Exception as e:
                final_output += f"\n   - (조회 실패: {str(e)})"

        # [Case 2] 경기 (기존 유지)
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

        # [Case 3] 전국 (기존 유지)
        if "[서울]" not in final_output and "[경기]" not in final_output:
            if "📍" not in final_output: 
                final_output += f"\n\n📍 {station_name} {ars_display} [전국]"
            request_url = f"{url_national}?serviceKey={ENCODING_KEY}"
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
                    final_output += "\n   💤 도착 예정 버스 없음 (또는 조회 실패)"
            
    return final_output

# 실행부
TOOLS = [{"name": "get_bus_arrival", "description": "버스 도착 정보 및 방향 분석", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}, "func": get_bus_arrival}]
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