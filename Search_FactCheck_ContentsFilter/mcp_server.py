# MCP 서버 모듈
# 외부 클라이언트(Cursor 등)와 연결되는 진입점으로, 전체 팩트체크 및 콘텐츠 필터링 파이프라인을 오케스트레이션합니다.

import grpc
from mcp.server.fastmcp import FastMCP

import agents_pb2
import agents_pb2_grpc

# FastMCP 인스턴스 생성 - MCP 프로토콜을 통해 도구를 제공합니다
mcp = FastMCP(name="grpc_agents")

# gRPC 채널과 스텁을 저장할 전역 변수
# 채널: 각 에이전트 서비스와의 연결
# 스텁: 각 서비스를 호출하기 위한 클라이언트 객체
channels = {}
stubs = {}

async def boot():
    """Refiner 서비스에 대한 gRPC 채널과 스텁을 초기화합니다."""
    global channels, stubs

    # 이미 초기화되어 있으면 재초기화하지 않음
    if stubs:
        return

    # Refiner 서비스에 대한 비동기 gRPC 채널 생성
    # 에이전트 간 직접 통신 구조에서는 Refiner만 MCP 서버에서 직접 호출됩니다
    channels["refiner"] = grpc.aio.insecure_channel("localhost:50051")

    # 각 서비스에 대한 스텁 생성 - 이를 통해 서비스를 호출할 수 있습니다
    # 에이전트 간 직접 통신 구조에서는 Refiner만 MCP 서버에서 직접 호출됩니다
    stubs["refiner"]=agents_pb2_grpc.RefinerServiceStub(channels["refiner"])
    # 나머지 에이전트들은 다른 에이전트들에 의해 직접 호출되므로 MCP 서버에서는 스텁을 생성하지 않습니다

@mcp.tool(name="ask", description="전체 gRPC 파이프라인 실행")
async def ask_tool(input):
    """
    질문에서 최종 응답까지의 전체 파이프라인을 실행합니다.
    
    에이전트 간 직접 통신 구조:
    - MCP 서버는 Refiner의 Process 메서드만 호출
    - Refiner가 Responder와 FactChecker를 병렬 호출
    - Refiner가 HalluService의 AnalyzeAndFinalize를 호출
    - HalluService가 내부에서 Finalizer를 호출하여 최종 응답 생성
    """
    # gRPC 채널과 스텁 초기화
    await boot()
    if isinstance(input, str):
        input = {"question": input}
    elif not isinstance(input, dict):
        return {"ok": False, "error": "invalid input format"}
    # 사용자 질문 추출 및 공백 제거
    q = input.get("question","").strip()

    # Refiner의 Process 메서드를 호출하여 전체 파이프라인 실행
    # 에이전트 간 직접 통신을 통해 처리됩니다
    final = await stubs["refiner"].Process(
        agents_pb2.RefineRequest(user_question=q)
    )

    # 최종 결과 반환
    return {
        "ok":True,
        "final":final.final_answer       # 최종 응답 (신뢰도 정보, 출처 포함)
    }

if __name__=="__main__":
    # MCP 서버를 stdio 전송 방식으로 실행
    # Cursor 등 MCP 클라이언트와 통신합니다
    mcp.run(transport="stdio")
