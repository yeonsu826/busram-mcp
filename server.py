from mcp.server.fastmcp import FastMCP
import requests
import urllib.parse
import uvicorn

# 1. 서버 이름 설정
mcp = FastMCP("BusAlert")

# 2. 님의 키 (Encoding 키)
ENCODING_KEY = "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D"

# 공공데이터포털은 Decoding된 키를 원하므로 미리 변환
DECODING_KEY = urllib.parse.unquote(ENCODING_KEY)

@mcp.tool()
def search_station(keyword: str) -> str:
    """
    [1단계] 정류장 이름을 검색해서 ID를 찾습니다.
    예: "강남역"을 검색하면 정류장 ID와 도시 코드를 알려줍니다.
    Args:
        keyword: 검색할 정류장 이름 (예: 강남역)
    """
    # 국토교통부 정류소 검색 API
    url = "http://apis.data.go.kr/1613000/BusSttnInfoInqireService/getSttnNoList"
    
    # 1005번 버스는 경기(31) 버스지만 서울(11) 정류장에도 섭니다.
    # 정확도를 위해 서울(11)과 경기(31)를 모두 검색해보는 게 좋습니다.
    # 일단 서울(11) 기준으로 검색합니다.
    params = {
        "serviceKey": DECODING_KEY,
        "cityCode": "11", # 서울
        "nodeNm": keyword,
        "numOfRows": 5,
        "_type": "json"
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        items = data['response']['body']['items']['item']
        if not items:
            return "검색 결과가 없습니다."
            
        # 리스트가 아니면 리스트로 변환 (데이터가 1개일 때 에러 방지)
        if isinstance(items, dict):
            items = [items]
            
        result = f"🔍 '{keyword}' 검색 결과:\n"
        for item in items:
            name = item.get('nodeNm')
            node_id = item.get('nodeid') # 중요: 이게 있어야 도착정보 조회 가능
            ars_id = item.get('nodeno')
            result += f"- {name} (ID: {node_id}) / 정류장번호: {ars_id}\n"
            
        return result
        
    except Exception as e:
        return f"에러 발생: {str(e)}"

@mcp.tool()
def check_arrival(city_code: str, station_id: str) -> str:
    """
    [2단계] 특정 정류장에 오는 버스들의 도착 정보를 조회.
    Args:
        city_code: 도시 코드 (서울: 11, 경기: 31, 세종: 12 등)
        station_id: search_station에서 찾은 정류장 ID (예: DJB8001793)
    """
    # 아까 성공한 국토교통부 도착 정보 API (오타 수정된 버전!)
    url = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList"
    
    params = {
        "serviceKey": DECODING_KEY,
        "cityCode": city_code,
        "nodeId": station_id,
        "numOfRows": 10,
        "_type": "json"
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        items = data['response']['body']['items']['item']
        if not items:
            return "현재 도착 예정인 버스가 없습니다."
            
        if isinstance(items, dict):
            items = [items]
            
        result = f"🚌 정류장(ID:{station_id}) 도착 정보:\n"
        for item in items:
            bus_num = item.get('routeno') # 버스 번호
            left_station = item.get('arrprevstationcnt') # 남은 정거장 수
            left_time = item.get('arrtime') # 남은 시간(초)
            
            # 초를 분으로 변환
            min_left = int(left_time) // 60
            
            result += f"- [{bus_num}번] {min_left}분 후 도착 ({left_station}정거장 전)\n"
            
        return result

    except Exception as e:
        return f"도착 정보 조회 실패: {str(e)}"
    


if __name__ == "__main__":
    # 'sse'는 웹 브라우저로 접속할 수 있게 해주는 모드
    mcp.run(transport='sse')


app = mcp._http_server
