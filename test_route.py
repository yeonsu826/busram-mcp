import requests
import json

# ⚠️ Render 서버 주소 (끝에 /mcp 필수)
RENDER_URL = "https://busram-mcp.onrender.com/mcp"

def test_tool(tool_name: str, args: dict) -> None:
    """
    서버에 특정 도구(Tool) 실행을 요청하고 결과를 출력하는 함수
    """
    print(f"\n🚀 원격 서버에 '{tool_name}' 실행 요청 중... (인자: {args})")
    
    # MCP 프로토콜 JSON-RPC 메시지
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args
        },
        "id": 1
    }

    try:
        response = requests.post(RENDER_URL, json=payload, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ HTTP 에러: {response.status_code}")
            print(response.text)
            return

        result = response.json()
        
        # 에러 처리
        if "error" in result:
            print("❌ MCP 에러:", result["error"]["message"])
            return

        # 정상 결과 출력
        if "result" in result and "content" in result["result"]:
            content = result["result"]["content"][0]["text"]
            print("="*50)
            print(content)
            print("="*50)
        else:
            print("⚠️ 예상치 못한 응답:", result)

    except Exception as e:
        print(f"❌ 연결 실패: {e}")

if __name__ == "__main__":
    # --- 테스트 시나리오 ---

    # 1. 정류장 도착 정보 조회 (기존 기능)
    test_tool("get_bus_arrival", {"keyword": "하림각"})

    # 2. [NEW] 버스 노선 전체 위치 조회 (새 기능)
    #    -> 7016번 버스가 지금 어디어디에 있는지 브리핑
    #test_tool("get_bus_route_info", {"bus_number": "7016"})