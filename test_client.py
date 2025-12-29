import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

# 👇 여기에 님의 Render 주소를 넣으세요 (뒤에 /sse 꼭 붙이기!)
SERVER_URL = "https://busram-mcp.onrender.com/mcp"

async def run_test():
    print(f"🔌 서버에 접속 시도 중... ({SERVER_URL})")
    
    try:
        # 1. 서버와 연결 (AI가 접속하는 것과 똑같음)
        async with sse_client(SERVER_URL) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                print("✅ 서버 연결 성공! (AI가 접속했습니다)")

                # 2. 도구 목록 확인 (메뉴판 달라고 하기)
                tools = await session.list_tools()
                print(f"\n📋 발견된 도구(Tools): {[t.name for t in tools.tools]}")

                # 3. 'search_station' 도구 써보기 (종로1가 검색)
                print("\n🤖 AI: '종로1가 정류장 찾아줘' (명령 보냄)")
                result1 = await session.call_tool("search_station", arguments={"keyword": "종로1가"})
                
                print(f"📨 서버 응답:\n{result1.content[0].text}")

                # 4. 'check_arrival' 도구 써보기 (위에서 찾은 ID로 도착 정보 조회)
                # (테스트를 위해 종로1가 ID 100000386 직접 입력)
                print("\n🤖 AI: 'ID 100000386 버스 언제 와?' (명령 보냄)")
                result2 = await session.call_tool("check_arrival", arguments={
                    "city_code": "11",
                    "station_id": "100000386"
                })
                
                print(f"📨 서버 응답:\n{result2.content[0].text}")
                
    except Exception as e:
        print(f"❌ 접속 실패: {e}")
        print("팁: 주소 뒤에 /mcp 를 붙였는지, https가 맞는지 확인하세요.")

if __name__ == "__main__":
    # 비동기 실행을 위한 설정
    asyncio.run(run_test())