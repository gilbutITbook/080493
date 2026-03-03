# 팩트체크 에이전트 모듈
# Tavily Search API를 사용하여 정제된 질문에 대한 실시간 정보 검증을 수행합니다.

import os, sys
# 상위 디렉토리를 Python 경로에 추가하여 agents_pb2 모듈을 import할 수 있도록 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import grpc
import asyncio

# Tavily Search API를 사용하기 위한 LangChain 통합 패키지
from langchain_tavily import TavilySearch

import agents_pb2
import agents_pb2_grpc

# 환경 변수 로드 (.env 파일에서 API 키를 읽어옴)
from dotenv import load_dotenv
load_dotenv()

class FactCheckerService(agents_pb2_grpc.FactCheckerServiceServicer):
    """
    팩트체크 서비스 클래스
    gRPC 서비스로 구현되어 있으며, 질문에 대한 팩트 검증을 수행합니다.
    """
    def __init__(self):
        """서비스 초기화 - Tavily API 키 검증 및 검색 도구 생성"""
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            raise RuntimeError("TAVILY_API_KEY not set")

        # Tavily Search 도구 초기화
        # max_results=10으로 설정하여 최대 10개의 검색 결과를 가져옵니다
        self.tool = TavilySearch(
            api_key=key,
            max_results=10
        )

    async def Check(self, request, context):
        """
        팩트체크 메서드
        정제된 질문을 받아 Tavily Search를 통해 관련 정보를 검색하고 검증합니다.
        """
        # 정제된 질문 추출 및 공백 제거
        q = request.refined.strip()

        try:
            # Tavily Search API를 통해 질문에 대한 검색 수행
            result_dict = self.tool.invoke(q)
        except Exception as e:
            # API 호출 실패 시 에러 로그 출력 및 빈 결과 반환
            print("!! Tavily error:", e)
            return agents_pb2.FactCheckResponse(
                facts=[],
                sources=[],
                verification_status="unverifiable"
            )

        # 검색 결과에서 results 리스트 추출
        # Tavily API는 딕셔너리 형태로 결과를 반환합니다
        results = result_dict.get("results", [])

        # 팩트와 출처를 저장할 리스트와 집합 초기화
        facts = []
        srcs = set()

        # 검색 결과 중 최대 8개까지 처리
        for r in results[:8]:
            # 각 결과에서 콘텐츠와 URL 추출
            content = r.get("content") or ""
            url = r.get("url") or ""

            # 콘텐츠가 50자 이상인 경우에만 팩트로 인정
            # 너무 짧은 내용은 유용하지 않을 수 있습니다
            if len(content) > 50:
                # 팩트 객체 생성 (콘텐츠는 최대 300자로 제한)
                facts.append(
                    agents_pb2.Fact(
                        content=content[:300],
                        url=url
                    )
                )
                # 출처 URL을 집합에 추가 (중복 제거)
                srcs.add(url)

        # 팩트가 있으면 "verified", 없으면 "unverifiable"로 상태 설정
        status = "verified" if facts else "unverifiable"

        # gRPC 응답 반환
        return agents_pb2.FactCheckResponse(
            facts=facts,                    # 검증된 팩트 리스트
            sources=list(srcs),             # 출처 URL 리스트 
            verification_status=status       # 검증 상태
        )

async def serve():
    """
    gRPC 서버 실행 함수
    팩트체크 서비스를 gRPC 서버로 실행합니다.
    """
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # FactCheckerService를 서버에 등록
    agents_pb2_grpc.add_FactCheckerServiceServicer_to_server(
        FactCheckerService(), server
    )
    # 포트 50053에서 서비스 시작 (모든 인터페이스에서 수신)
    server.add_insecure_port("[::]:50053")
    await server.start()
    print("FactCheckerService ON 50053")
    # 서버 종료 대기
    await server.wait_for_termination()

if __name__ == "__main__":
    # 직접 실행 시 서버 시작
    asyncio.run(serve())
