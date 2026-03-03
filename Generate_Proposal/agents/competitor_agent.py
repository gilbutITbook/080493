# competitor_agent.py
# 경쟁사 분석 에이전트 모듈
# LLM을 사용하여 특정 회사와 시장에 대한 경쟁사 분석을 수행합니다.
from __future__ import annotations
import os
import grpc
import asyncio

from openai import AsyncOpenAI

import agents_pb2
import agents_pb2_grpc

class CompetitorSearchAgent:
    """경쟁사 검색 및 분석을 수행하는 에이전트 클래스"""
    def __init__(self):
        # 환경변수에서 OpenAI API 키를 가져옴
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            # API 키가 있으면 AsyncOpenAI 클라이언트 초기화
            self.client = AsyncOpenAI(api_key=api_key)
        else:
            # API 키가 없으면 None으로 설정 (LLM 없이 동작 가능)
            self.client = None
    
    async def run(self, company: str, market: str, topk: int = 5):
        """LLM으로 경쟁사 분석 수행"""
        try:
            # LLM이 없으면 기본 메시지 반환
            if not self.client:
                return f"{company}의 경쟁사 분석 결과 (top {topk}) in {market}\n\n(LLM 분석을 위해 OPENAI_API_KEY 환경변수를 설정해주세요)"
            
            # 경쟁사 분석을 위한 프롬프트 구성
            # 회사명, 시장, 상위 경쟁사 개수를 포함한 상세한 분석 요청
            prompt = f"""다음 회사와 시장에 대한 경쟁사 분석을 수행해주세요:

회사: {company}
시장: {market}
상위 {topk}개 경쟁사 분석 요청

각 경쟁사의 다음 정보를 포함하여 영어로 작성해주세요:
1. 회사명 및 주요 제품/서비스
2. 시장 점유율 및 위치
3. 주요 강점 및 차별화 요소
4. {company}와의 비교 분석
5. 시장에서의 경쟁 우위/열위

특히 {market} 시장에서의 경쟁 상황을 중점적으로 분석해주세요."""

            # OpenAI API를 통해 경쟁사 분석 요청
            # gpt-5.2 모델 사용, temperature 0.7로 창의성과 일관성의 균형 유지
            response = await self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "당신은 시장 분석 전문가입니다. 정확하고 상세한 경쟁사 분석을 제공합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            
            # 응답에서 분석 결과 추출
            if not response or not response.choices or len(response.choices) == 0:
                return f"{company}의 경쟁사 분석 결과 (top {topk}) in {market}\n\n(LLM 응답이 비어있습니다)"
            
            analysis = response.choices[0].message.content
            if not analysis:
                return f"{company}의 경쟁사 분석 결과 (top {topk}) in {market}\n\n(LLM 응답 내용이 없습니다)"
            
            return analysis
            
        except Exception as e:
            # 예외 발생 시 상세한 오류 메시지 반환
            import traceback
            error_detail = traceback.format_exc()
            return f"{company}의 경쟁사 분석 결과 (top {topk}) in {market}\n\n경쟁사 분석 중 오류 발생: {str(e)}\n\n{error_detail}"

class CompetitorService(agents_pb2_grpc.CompetitorServiceServicer):
    """gRPC 서비스 - 경쟁사 분석 서비스 구현"""
    def __init__(self):
        # CompetitorSearchAgent 인스턴스 생성
        self.agent = CompetitorSearchAgent()
        # 다음 에이전트 주소 설정
        self.formatter_addr = os.getenv("FORMATTER_ADDR", "localhost:6005")

    async def _call_formatter(self, text: str, profiles_path: str, question: str):
        """FormatterAgent 호출"""
        try:
            async with grpc.aio.insecure_channel(self.formatter_addr) as ch:
                stub = agents_pb2_grpc.FormatterServiceStub(ch)
                return await stub.FormatKo(
                    agents_pb2.FormatKoRequest(
                        text=text,
                        profiles_path=profiles_path,
                        question=question
                    )
                )
        except Exception as e:
            return agents_pb2.FormatKoResponse(ok=False, error=str(e))

    async def Search(self, req, ctx):
        """gRPC Search 메서드 - 경쟁사 검색 요청 처리"""
        try:
            # 에이전트의 run 메서드 호출하여 경쟁사 분석 수행
            out = await self.agent.run(req.company, req.market, req.topk)
            
            # 빈 문자열이나 None 체크 (공백만 있는 경우도 체크)
            if not out or not out.strip():
                return agents_pb2.CompetitorSearchResponse(
                    ok=False, 
                    error=f"경쟁사 분석 실패: 분석 결과가 비어있습니다. (out={repr(out)})"
                )
            
            # FormatterAgent를 직접 호출하여 한국어로 변환 (컨텍스트 전달)
            profiles_path = getattr(req, 'profiles_path', '') or os.getenv("PROFILES_PATH", "")
            question = getattr(req, 'question', '') or os.getenv("QUESTION", "")
            
            fmt = await self._call_formatter(out, profiles_path, question)
            if not fmt.ok:
                return agents_pb2.CompetitorSearchResponse(
                    ok=False, 
                    error=f"FormatterAgent 호출 실패: {fmt.error}"
                )
            
            competitor_ko = fmt.value
            
            # FormatterAgent가 CustomerAgent를 호출하도록 컨텍스트 전달
            # (FormatterAgent 내부에서 처리되므로 여기서는 결과만 반환)
            return agents_pb2.CompetitorSearchResponse(ok=True, raw_en=competitor_ko)
        except Exception as e:
            # 실패 응답 반환 (오류 메시지 포함)
            import traceback
            error_detail = traceback.format_exc()
            return agents_pb2.CompetitorSearchResponse(
                ok=False, 
                error=f"Search 메서드 실행 중 예외 발생: {str(e)}\n\n{error_detail}"
            )

async def serve(port: int = None):
    """gRPC 서버 시작 함수"""
    # 포트 설정: 인자로 전달된 포트 또는 환경변수 또는 기본값 6001
    port = port or int(os.getenv("COMPETITOR_PORT", "6001"))
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # CompetitorService를 서버에 등록
    agents_pb2_grpc.add_CompetitorServiceServicer_to_server(
        CompetitorService(), server
    )
    # 서버를 지정된 포트에 바인딩 (모든 인터페이스에서 접근 가능)
    server.add_insecure_port(f"0.0.0.0:{port}")
    # 서버 시작
    await server.start()
    print(f"[CompetitorService] running on port {port}", flush=True)
    # 서버 종료 대기
    await server.wait_for_termination()

# 직접 실행 시 gRPC 서버를 시작하는 진입점
if __name__ == "__main__":
    import argparse
    # 명령줄 인자 파서 생성
    parser = argparse.ArgumentParser()
    # 포트 오버라이드 옵션 추가
    parser.add_argument("--port", type=int, help="override port")
    args = parser.parse_args()

    # 서버 실행
    asyncio.run(serve(args.port))
