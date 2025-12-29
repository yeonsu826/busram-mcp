import requests

# ⚠️ 인코딩 키를 넣으세요
ENCODING_KEY = "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D"
def find_bus_safe(city_code, bus_name):
    print(f"🔎 {city_code}번 도시에서 [{bus_name}] 찾는 중...")

    base_url = "https://apis.data.go.kr/1613000/BusRouteInfoInqireService/getRouteNoList"
    url = f"{base_url}?serviceKey={ENCODING_KEY}"
    
    params = {
        "cityCode": city_code, 
        "routeNo": bus_name,   
        "numOfRows": 10,
        "_type": "json"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        
        try: 
            data = response.json()
        except:
            print("❌ JSON 변환 실패. 응답 내용:")
            print(response.text)
            return

        # 1. response 키 체크
        if 'response' not in data:
            print(f"❌ API 구조 에러 (response 키 없음): {data}")
            return
            
        header = data['response']['header']
        if header['resultCode'] != '00':
            print(f"❌ API 에러 메시지: {header['resultMsg']}")
            return

        body = data['response']['body']
        
        # 2. [핵심 수정] totalCount를 먼저 검사해서 0이면 바로 종료
        # (이게 0이면 items가 딕셔너리가 아니라 문자열 ""로 와서 에러가 났던 겁니다)
        total_count = body.get('totalCount', 0)
        print(f"📊 검색된 결과 수: {total_count}건")

        if total_count == 0:
            print("⚠️ 검색 결과가 없습니다.")
            return

        # 3. items 가져오기 (안전 장치 추가)
        items_container = body.get('items')
        
        if not items_container: # items가 None이거나 비어있으면
            print("⚠️ items 데이터가 비어있습니다.")
            return

        # items 안에 item이 있는지 확인
        if isinstance(items_container, str):
            print(f"⚠️ items가 문자열로 왔습니다 (구조 이상): {items_container}")
            return
            
        bus_list = items_container.get('item', [])

        # 결과가 1개일 때는 리스트가 아니라 딕셔너리로 오므로 리스트로 감싸줌
        if isinstance(bus_list, dict): 
            bus_list = [bus_list]

        print("-" * 30)
        for bus in bus_list:
            print(f"🚌 [{bus.get('routeno')}] {bus.get('routetp')}")
            print(f"   🆔 ID: {bus.get('routeid')}") 
            print(f"   ↔️ 구간: {bus.get('startnodenm')} ~ {bus.get('endnodenm')}")
            print("-" * 30)

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        # 디버깅을 위해 전체 데이터를 찍어봄
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    find_bus_safe("12", "720-2")