import requests
import json

SERVER_URL = "https://busram-mcp.onrender.com/mcp"
# 또는 사용자님의 Render 주소: "https://busram-mcp.onrender.com/mcp"



def test_tool(tool_name, args):
    print(f"\n🚀 Testing tool: {tool_name}...")
    try:
        res = requests.post(SERVER_URL, json={
            "jsonrpc": "2.0", "method": "tools/call", "id": 1,
            "params": {"name": tool_name, "arguments": args}
        }).json()
        print(res["result"]["content"][0]["text"])
    except Exception as e: print(f"❌ Error: {e}")

if __name__ == "__main__":
    # 1. 버스 위치 (성공했던 기능)
    test_tool("get_bus_location", {"bus_number": "7016"})
    
    # 2. 정류장 정보 (수정된 기능) -> 방향, 시간 나오는지 확인
    test_tool("get_station_arrival", {"keyword": "하림각"})