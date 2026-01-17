import requests
import json

SERVER_URL = "https://busram-mcp.onrender.com/mcp"
# 또는 사용자님의 Render 주소: "https://busram-mcp.onrender.com/mcp"

def test_tool(tool_name, args):
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
        print(f"🚀 Testing tool: {tool_name}...")
        response = requests.post(SERVER_URL, json=payload)
        response.raise_for_status()
        
        result = response.json()
        if "error" in result:
            print(f"❌ Error: {result['error']}")
        else:
            print("✅ Success!")
            print(result["result"]["content"][0]["text"])
            
    except Exception as e:
        print(f"❌ Request Failed: {e}")

if __name__ == "__main__":
    # [테스트 1] 7016번 버스 전체 현황 (위치 조회 대체 기능)
    test_tool("get_route_all_arrival", {"bus_number": "7016"})
    
    print("\n" + "="*30 + "\n")
    
    # [테스트 2] 하림각 정류장 도착 정보
    test_tool("get_station_arrival", {"station_name": "하림각"})