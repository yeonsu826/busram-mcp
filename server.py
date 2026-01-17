# =================================================================
# BusRam MCP Server (V16: Village Bus Fix - General API)
# =================================================================
import uvicorn
import requests
import pandas as pd
import os
import re
import json
from urllib.parse import unquote
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

# 🔑 [키 설정]
DECODED_KEY = "ezGwhdiNnVtd+HvkfiKgr/Z4r+gvfeUIRz/dVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI+/pJFoYr9Ce+TDg=="

print("📂 [System] 정류장 데이터 로딩 중...")
STATION_CSV = "station_data.csv"

try:
    try: df_stations = pd.read_csv(STATION_CSV, encoding='cp949')
    except: df_stations = pd.read_csv(STATION_CSV, encoding='utf-8')
    df_stations['정류장명'] = df_stations['정류장명'].astype(str)
    df_stations['clean_id'] = df_stations['정류장번호'].astype(str).apply(lambda x: re.sub(r'[^0-9]', '', x))
    print(f"✅ 정류장 데이터 로드 완료: {len(df_stations)}개")
except Exception as e:
    print(f"❌ 데이터 로드 실패: {e}")
    df_stations = pd.DataFrame()

# --- Tool 1: 통합 버스 도착 정보 (마을버스 지원 강화) ---
def get_bus_arrival(keyword: str) -> str:
    print(f"[검색 요청] '{keyword}'")
    
    if df_stations.empty: return "❌ 서버 오류: 데이터 파일 없음"

    mask = df_stations['정류장명'].str.contains(keyword)
    results = df_stations[mask].head(5)
    
    if results.empty: return f"❌ '{keyword}' 검색 결과가 없습니다."
    
    final_output = f"🚏 **'{keyword}' 검색 결과**\n"
    
    # 🚨 [핵심 수정] 저상버스 API(getLow...) -> 일반 도착정보 API(getArr...)로 변경
    # 이 API가 마을버스 데이터를 훨씬 잘 가져옵니다.
    url = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByUid"
    
    for _, row in results.iterrows():
        st_name = row['정류장명']
        raw_id = row['정류장번호']
        st_id = re.sub(r'[^0-9]', '', str(raw_id)) # 정류장 고유 ID (9자리)
        
        # ARS ID (5자리 표기용)
        ars_display = row.get('모바일단축번호', '')
        if pd.isna(ars_display) or not str(ars_display).strip(): 
            ars_display = "(ID없음)"
        else:
            ars_display = str(int(float(ars_display))).zfill(5)

        final_output += f"\n📍 **{st_name}** ({ars_display})"
        
        try:
            # stId: 정류소 고유 ID (필수)
            params = {"serviceKey": DECODED_KEY, "stId": st_id, "resultType": "json"}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if 'msgBody' in data and data['msgBody']['itemList']:
                items = data['msgBody']['itemList']
                if isinstance(items, dict): items = [items]
                
                # 도착 정보 파싱
                count = 0
                for bus in items:
                    rt_nm = bus.get('rtNm', '?')
                    msg1 = bus.get('arrmsg1', '정보없음')
                    
                    # 도착 정보가 있는 버스만 표시
                    if msg1 != '운행종료' and msg1 != '출발대기':
                        final_output += f"\n   🚌 **{rt_nm}**: {msg1}"
                        count += 1
                
                if count == 0: final_output += "\n   (운행 종료 또는 도착 정보 없음)"

            else:
                # API는 성공했으나(200 OK), 데이터 리스트가 비어있는 경우
                final_output += "\n   (도착 예정 버스 없음)"
                
        except Exception as e:
            final_output += f"\n   ⚠️ 조회 에러 ({str(e)})"
            
    return final_output

# -----------------------------------------------------------------
# 🚀 핸들러
# -----------------------------------------------------------------
TOOLS = [
    {
        "name": "get_bus_arrival", 
        "description": "정류장 이름을 입력받아 시내버스와 마을버스의 실시간 도착 정보를 조회합니다.", 
        "inputSchema": {
            "type": "object", 
            "properties": {"keyword": {"type": "string", "description": "정류장 이름 (예: 하림각, 서울역)"}}, 
            "required": ["keyword"]
        }, 
        "func": get_bus_arrival
    }
]

async def handle_request(request):
    if request.method == "GET": return JSONResponse({"status": "BusRam V16 Online"})
    try:
        body = await request.json()
        if body.get("method") == "initialize": 
            return JSONResponse({"jsonrpc": "2.0", "id": body.get("id"), "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "BusRam", "version": "1.0.6"}}})
        elif body.get("method") == "tools/list": 
            return JSONResponse({"jsonrpc": "2.0", "id": body.get("id"), "result": {"tools": [{k: v for k, v in t.items() if k != 'func'} for t in TOOLS]}})
        elif body.get("method") == "tools/call":
            tool = next((t for t in TOOLS if t["name"] == body["params"]["name"]), None)
            if tool:
                res = await run_in_threadpool(tool["func"], **body["params"]["arguments"])
                return JSONResponse({"jsonrpc": "2.0", "id": body.get("id"), "result": {"content": [{"type": "text", "text": res}]}})
    except: pass
    return JSONResponse({"error": "Error"}, status_code=500)

app = Starlette(debug=True, routes=[Route("/", endpoint=handle_request, methods=["POST", "GET"]), Route("/mcp", endpoint=handle_request, methods=["POST", "GET"])], middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))