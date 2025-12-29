import requests
import urllib.parse

# ⚠️ 여기에 본인의 'Decoding' 키를 꼭 붙여넣으세요!
DECODING_KEY = "ezGwhdiNnVtd+HvkfiKgr/Z4r+gvfeUIRz/dVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI+/pJFoYr9Ce+TDg=="

def search_station_test(keyword: str):
    print(f"🚀 검색 시작: {keyword}")
    
    # 원본 코드와 동일한 로직
    url = "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/getSttnNoList"
    params = {
        "serviceKey": DECODING_KEY, 
        "cityCode": "11",  # 서울
        "nodeNm": keyword, 
        "numOfRows": 5, 
        "_type": "json"
    }

    try:
        # 1. API 요청 보내기
        response = requests.get(url, params=params, timeout=10)
        print(f"📡 응답 상태 코드: {response.status_code}")

        # 2. JSON 변환 시도
        try: 
            data = response.json()
        except: 
            print("❌ JSON 변환 실패. 응답 내용 확인:")
            print(response.text)
            return

        # 3. 에러 체크
        if 'response' not in data: 
            print(f"❌ API Error: {data}")
            return
        
        # 4. 결과 개수 확인
        total_count = data['response']['body']['totalCount']
        if total_count == 0: 
            print("❌ 검색 결과가 없습니다.")
            return

        # 5. 아이템 파싱
        items = data['response']['body']['items']['item']
        if isinstance(items, dict): 
            items = [items]
        
        # 6. 결과 출력
        print(f"✅ 검색 성공! ({len(items)}개 발견)")
        for item in items:
            print(f" - 정류장명: {item.get('nodeNm')}") 
            print(f"   ID: {item.get('nodeid')}")
            print(f"   ARS번호: {item.get('nodeno')}")
            print("-" * 20)
            
    except Exception as e: 
        print(f"❌ 에러 발생: {str(e)}")

# 실제 테스트 실행
if __name__ == "__main__":
    search_station_test("서울역") # 원하는 정류장 이름으로 변경해서 테스트