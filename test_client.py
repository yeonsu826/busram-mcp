import requests
import json
import os

# ⚠️ 본인의 [Encoding] 키를 넣으세요
ENCODING_KEY = "ezGwhdiNnVtd%2BHvkfiKgr%2FZ4r%2BgvfeUIRz%2FdVqEMTaJuAyXxGiv0pzK0P5YT37c4ylzS7kI%2B%2FpJFoYr9Ce%2BTDg%3D%3D"

def check_api_permissions():
    print("🏥 [API 진단] 내 키로 서울/경기 데이터가 나오는지 확인합니다...\n")

    # 1. 경기도 API 테스트 (판교역)
    print(" 경기도 API (판교역) 테스트 중...")
    url_gg = "http://apis.data.go.kr/6410000/busarrivalservice/getBusArrivalList"
    params_gg = {
        "serviceKey": ENCODING_KEY,
        "stationId": "206000233"  # 판교역서편 ID (경기도 전용)
    }
    try:
        res = requests.get(url_gg, params=params_gg, timeout=5)
        # 경기도는 보통 XML을 주지만, 에러면 HTML/JSON이 올 수도 있음
        if "<busArrivalList>" in res.text:
            print("   ✅ 성공! (경기도 API 권한 있음)")
            print("   👉 'Ultimate(완전체)' 코드를 쓰시면 판교역 잘 나옵니다.")
        elif "SERVICE_ACCESS_DENIED" in res.text or "SERVICE_KEY_IS_NOT_REGISTERED" in res.text:
            print("   ❌ 실패 (인증 에러)")
            print("   👉 공공데이터포털에서 [경기도_버스도착정보조회] 신청 필요")
        else:
            print(f"   ⚠️ 응답 확인 필요: {res.text[:100]}...")
    except Exception as e:
        print(f"   ❌ 에러 발생: {e}")
    print("-" * 40)

    # 2. 서울시 API 테스트 (강남역)
    print("서울시 API (강남역) 테스트 중...")
    url_seoul = "http://ws.bus.go.kr/api/rest/stationinfo/getStationByUid"
    params_seoul = {
        "serviceKey": ENCODING_KEY,
        "arsId": "22009",  # 강남역 ARS 번호
        "resultType": "json"
    }
    try:
        res = requests.get(url_seoul, params=params_seoul, timeout=5)
        try:
            data = res.json()
            if 'msgBody' in data:
                print("   ✅ 성공! (서울시 API 권한 있음)")
                print("   👉 'Ultimate(완전체)' 코드를 쓰시면 강남역 잘 나옵니다.")
            else:
                print("   ❌ 실패 (데이터 구조 다름)")
        except:
            # JSON 변환 실패면 보통 에러 메시지(XML)임
            if "SERVICE_ACCESS_DENIED" in res.text:
                print("   ❌ 실패 (인증 에러)")
                print("   👉 공공데이터포털에서 [서울특별시_버스도착정보조회] 신청 필요")
            else:
                print(f"   ⚠️ 응답: {res.text[:100]}")
    except Exception as e:
        print(f"   ❌ 에러 발생: {e}")
    print("-" * 40)

if __name__ == "__main__":
    check_api_permissions()