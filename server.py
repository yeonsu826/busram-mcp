# =================================================================
# BusRam MCP Server (Ultimate Fix: Zero Padding)
# =================================================================
import uvicorn
import requests
import pandas as pd
import os
import json
import re
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# 1. 설정 및 CSV 데이터 로드
ENCODING_KEY = os.environ.get("ENCODING_KEY", "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D")

print("📂 [System] 정류장 데이터(CSV) 로딩 중...")
CSV_PATH = "station_data.csv"

try:
    try:
        df_stations = pd.read_csv(CSV_PATH, encoding='cp949')
    except:
        df_stations = pd.read_csv(CSV_PATH, encoding='utf-8')

    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    df_stations['도시코드'] = df_stations['도시코드'].astype(str)
    df_stations['정류장번호'] = df_stations['정류장번호'].astype(str)
    
    print(f"✅ [System] 데이터 로드 완료! 총 {len(df_stations)}개 정류장 대기 중.")

except Exception as e:
    print(f"❌ [Critical] CSV 파일 로드 실패: {e}")
    df_stations = pd.DataFrame()


# 2. 도구(Tool) 함수 정의
def get_bus_arrival(keyword: str) -> str:
    print(f"[Tool] '{keyword}' 검색 시작")
    
    if df_stations.empty: return "❌ 서버 에러: CSV 파일 로드 실패"

    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask]
    
    if results.empty: return f"❌ '{keyword}' 검색 결과가 없습니다."
    
    targets = results.head(4)
    final_output = f"🚏 '{keyword}' 도착 정보:\n"
    
    url_national = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList"
    url_seoul = "http://ws.bus.go.kr/api/rest/stationinfo/getStationByUid"
    url_gyeonggi = "http://apis.data.go.kr/6410000/busarrivalservice/getBusArrivalList"
    
    for _, row in targets.iterrows():
        station_name = row['정류장명']
        city_code = row['도시코드']
        raw_id = row['정류장번호']
        
        # 🟢 [핵심 수정] ARS 번호 5자리 맞추기 (0 채우기)
        ars_raw = row.get('모바일단축번호', '')
        ars_id = ""
        try:
            if pd.notnull(ars_raw) and str(ars_raw).strip() != "":
                # int로 변환 후 다시 str로 만들고, 5자리가 될 때까지 앞에 '0'을 붙임
                # 예: 1136 -> "01136"
                ars_id = str(int(float(ars_raw))).zfill(5)
        except: pass

        ars_display = f"(ARS: {ars_id})" if ars_id else ""
        station_id = re.sub(r'[^0-9]', '', raw_id) 
        
        # [Case 1] 서울
        if city_code == '11' and ars_id:
            final_output += f"\n📍 {station_name} {ars_display} [서울]\n"
            request_url = f"{url_seoul}?serviceKey={ENCODING_KEY}"
            params = {"arsId": ars_id, "resultType": "json"}
            
            try:
                response = requests.get(request_url, params=params, timeout=5)
                data = response.json()
                
                if 'msgBody' not in data or not data['msgBody']['itemList']:
                    final_output += "   💤 도착 예정 버스 없음\n"
                    continue
                
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                
                for bus in items:
                    rt_nm = bus.get('rtNm')
                    msg1 = bus.get('arrmsg1')
                    final_output += f"   🚌 [{rt_nm}번] {msg1}\n"

            except Exception:
                final_output += "   - (서울 데이터 조회 실패)\n"

        # [Case 2] 경기
        elif city_code.startswith('31') or city_code == '12': 
            final_output += f"\n📍 {station_name} {ars_display} [경기]\n"
            request_url = f"{url_gyeonggi}?serviceKey={ENCODING_KEY}"
            params = {"stationId": station_id}
            
            try:
                response = requests.get(request_url, params=params, timeout=5)
                try: 
                    data = response.json()
                    items = data['response']['msgBody']['busArrivalList']
                except:
                    final_output += "   - (API 응답 형식 오류: XML 파싱 필요)\n"
                    continue

                if isinstance(items, dict): items = [items]
                if not items:
                    final_output += "   💤 도착 예정 버스 없음\n"
                    continue

                for bus in items:
                    min_left = bus.get('predictTime1')
                    stops_left = bus.get('locationNo1')
                    final_output += f"   🚌 [버스] {min_left}분 후 ({stops_left}전)\n"
            except Exception:
                 pass
            if "버스" not in final_output: pass

        # [Case 3] 전국 (Fallback)
        if "[서울]" not in final_output and "[경기]" not in final_output:
            final_output += f"\n📍 {station_name} {ars_display} [전국]\n"
            request_url = f"{url_national}?serviceKey={ENCODING_KEY}"
            params = {"cityCode": city_code, "nodeId": station_id, "numOfRows": 5, "_type": "json"}
            
            try:
                response = requests.get(request_url, params=params, timeout=5)
                data = response.json()
                
                if data['response']['body']['totalCount'] == 0:
                    final_output += "   💤 도착 예정 버스 없음\n"
                    continue
                
                items = data['response']['body']['items']['item']
                if isinstance(items, dict): items = [items]
                
                for bus in items:
                    route_no = bus.get('routeno')
                    arr_time = bus.get('arrtime')
                    min_left = int(arr_time) // 60
                    msg = bus.get('arrmsg1', '')
                    final_output += f"   🚌 [{route_no}번] {min_left}분 후 ({msg})\n"
            except Exception:
                final_output += "   - (정보 조회 실패)\n"
            
    return final_output

# (나머지 TOOLS, handle_mcp_request, app 실행 부분은 기존과 동일)
TOOLS = [{"name": "get_bus_arrival", "description": "...", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}, "func": get_bus_arrival}]
async def handle_mcp_request(request):
    try:
        body = await request.json(); method = body.get("method"); msg_id = body.get("id")
        if method == "initialize": return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "BusRam", "version": "1.0.0"}}})
        elif method == "tools/list": return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]}})
        elif method == "tools/call":
            params = body.get("params", {}); tool_name = params.get("name"); args = params.get("arguments", {})
            tool = next((t for t in TOOLS if t["name"] == tool_name), None)
            if tool: return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": tool["func"](**args)}], "isError": False}})
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)
async def handle_root(request): return JSONResponse({"status": "ok", "service": "BusRam MCP"})
middleware = [Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]
app = Starlette(debug=True, routes=[Route("/mcp", endpoint=handle_mcp_request, methods=["POST"]), Route("/", endpoint=handle_root, methods=["GET"])], middleware=middleware)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)