import requests
import json

# ⚠️ 여기에 Render에서 발급받은 실제 주소를 넣으세요! (끝에 /mcp 포함)
RENDER_URL = "https://busram-mcp.onrender.com/mcp"

def test_remote_server(keyword: str) -> None:
    print(f"🚀 원격 서버({RENDER_URL})에 '{keyword}' 도착 정보 요청 중...")
    
    # MCP 프로토콜에 맞춘 JSON-RPC 요청 메시지
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "get_bus_arrival",  # 만든 도구 이름
            "arguments": {
                "keyword": keyword      # 검색어
            }
        },
        "id": 1
    }

    try:
        response = requests.post(RENDER_URL, json=payload, timeout=30)
        response.raise_for_status()  # HTTP 상태 코드 에러(4xx, 5xx) 확인
        
        print(f"📡 응답 상태: {response.status_code}")
        
        try:
            result = response.json()
            # 결과가 복잡하게 오는데, 우리가 원하는 텍스트는 result -> content -> text 안에 있음
            if "error" in result:
                print("❌ 서버 에러 발생:", result["error"])
            elif "result" in result:
                content = result["result"]["content"][0]["text"]
                print("\n" + "="*40)
                print(content)
                print("="*40 + "\n")
            else:
                print("⚠️ 예상치 못한 응답 형식입니다.")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
        except json.JSONDecodeError:
            print("❌ JSON 변환 실패. 서버 로그를 확인하세요.")
            print("응답 본문:", response.text)

    except Exception as e:
        print(f"❌ 요청 실패: {e}")

if __name__ == "__main__":
    # 버스가 24시간 많은 곳으로 테스트 (방향 기능 확인용)
    test_remote_server("서울역") 
    