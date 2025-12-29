import requests

# ⚠️ [중요] 여기에 'Encoding' 키를 넣으세요! (% 문자가 포함된 긴 키)
ENCODING_KEY = "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D"

def search_station_final_test(keyword: str):
    print(f"🚀 검색 시작: {keyword}")

    # 1. 기본 URL
    base_url = "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/getSttnNoList"
    
    # 2. [핵심 수정] 키를 params가 아니라 URL 뒤에 직접 붙입니다.
    # 이렇게 하면 파이썬이 키를 멋대로 건드리지 않습니다.
    url = f"{base_url}?serviceKey={ENCODING_KEY}"
    
    # 3. 나머지 파라미터 설정 (serviceKey 제외)
    params = {
        "cityCode": "11",   # 서울
        "nodeNm": keyword, 
        "numOfRows": 5, 
        "_type": "json"
    }

    try:
        # 4. 요청 보내기
        response = requests.get(url, params=params, timeout=10)
        
        # 디버깅: 실제로 날아가는 주소를 눈으로 확인
        print(f"🔗 실제 요청 URL: {response.url}")
        print(f"📡 응답 코드: {response.status_code}")

        # 5. 데이터 확인
        try:
            data = response.json()
        except:
            print("❌ JSON 변환 실패. 응답 텍스트:")
            print(response.text)
            return

        # 6. 결과 분석
        if 'response' not in data:
            print(f"❌ API 구조 에러: {data}")
            return
            
        total_count = data['response']['body']['totalCount']
        
        if total_count == 0:
            print("❌ 여전히 결과가 0건입니다.")
            print("👉 1. 활용신청한 API가 [국토교통부 버스정류소정보]가 맞는지 확인하세요.")
            print("👉 2. 키 발급 후 1시간이 지났는지 확인하세요.")
            return

        items = data['response']['body']['items']['item']
        if isinstance(items, dict): items = [items]

        print(f"✅ 성공! {len(items)}개의 정류장을 찾았습니다.")
        for item in items:
            print(f"- {item.get('nodeNm')} (ID: {item.get('nodeid')})")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    search_station_final_test("판교")