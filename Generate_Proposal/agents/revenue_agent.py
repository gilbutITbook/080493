# revenue_agent.py
# 수익모델 에이전트 모듈
# 제안된 기능을 바탕으로 현실적이고 실행 가능한 수익모델을 도출합니다.
from __future__ import annotations
import os
import grpc
import asyncio

from openai import AsyncOpenAI

import agents_pb2
import agents_pb2_grpc


class RevenueModelAgent:
    """수익모델 도출을 수행하는 에이전트 클래스"""
    def __init__(self):
        # 환경변수에서 OpenAI API 키를 가져옴
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            # API 키가 있으면 AsyncOpenAI 클라이언트 초기화
            self.client = AsyncOpenAI(api_key=api_key)
        else:
            # API 키가 없으면 None으로 설정 (LLM 없이 동작 가능)
            self.client = None
    
    async def model(self, features: str):
        """제안된 기능을 바탕으로 수익모델 도출"""
        try:
            # LLM이 없으면 기본 메시지 반환
            if not self.client:
                return {
                    "ok": True,
                    "revenue": f"수익모델 도출 결과:\n{features}\n\n(LLM 분석을 위해 OPENAI_API_KEY 환경변수를 설정해주세요)"
                }
            
            # 수익모델 도출을 위한 프롬프트 구성
            # 기능 제안을 바탕으로 가격 정책, 수익 구조, ROI 등을 포함한 수익모델 요청
            prompt = f"""다음 기능 제안을 바탕으로 수익모델을 도출해주세요:

[기능 제안]
{features}

위 기능 제안을 기반으로 다음을 포함한 수익모델을 한국어로 작성해주세요:
1. 가격 정책 (구독, 사용량 기반, 일회성 등)
2. 각 기능별 수익 구조
3. 예상 매출 및 수익성 분석
4. ROI (투자 대비 수익) 계산
5. 단계별 수익 목표 (1년, 3년, 5년)
6. 시장 규모 및 잠재 고객 수
7. 경쟁사 대비 가격 경쟁력
8. 고객 세그먼트별 수익 전략

구체적인 숫자와 근거를 포함하여 작성해주세요."""

            # OpenAI API를 통해 수익모델 도출 요청
            # gpt-5.2 모델 사용, temperature 0.7로 창의성과 일관성의 균형 유지
            response = await self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "당신은 비즈니스 모델 및 수익 분석 전문가입니다. 기능 제안을 바탕으로 현실적이고 실행 가능한 수익모델을 제시합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            
            # 응답에서 수익모델 내용 추출
            revenue_model = response.choices[0].message.content
            
            # 성공 응답 반환
            return {
                "ok": True,
                "revenue": revenue_model
            }
            
        except Exception as e:
            # 예외 발생 시 오류 정보 반환
            return {"ok": False, "error": str(e)}


class RevenueService(agents_pb2_grpc.RevenueServiceServicer):
    """gRPC 서비스 - 수익모델 서비스 구현"""
    def __init__(self):
        # RevenueModelAgent 인스턴스 생성
        self.agent = RevenueModelAgent()
        # 다음 에이전트 주소 설정
        self.writer_addr = os.getenv("WRITER_ADDR", "localhost:6006")

    async def _call_writer(self, company: str, market: str, question: str, customer: str, features: str, revenue: str, competitor: str, out_dir: str, filename: str | None):
        """WriterAgent 호출"""
        try:
            async with grpc.aio.insecure_channel(self.writer_addr) as ch:
                stub = agents_pb2_grpc.WriterServiceStub(ch)
                return await stub.PersistMd(
                    agents_pb2.PersistMdRequest(
                        company=company,
                        market=market,
                        question=question,
                        customer=customer,
                        features=features,
                        revenue=revenue,
                        competitor=competitor,
                        out_dir=out_dir,
                        filename=filename or ""  # None이면 빈 문자열로 변환
                    )
                )
        except Exception as e:
            return agents_pb2.PersistMdResponse(ok=False, error=str(e))

    async def Model(self, req, ctx):
        """gRPC Model 메서드 - 수익모델 도출 요청 처리"""
        try:
            # 에이전트의 model 메서드 호출하여 수익모델 도출 수행
            out = await self.agent.model(req.features)
            if not out.get("ok"):
                return agents_pb2.RevenueModelResponse(ok=False, error=out.get("error", "수익모델 도출 실패"))
            
            revenue_value = out["revenue"]
            
            # WriterAgent를 직접 호출하여 최종 마크다운 파일 저장
            company = getattr(req, 'company', '') or os.getenv("COMPANY", "Azure AI Foundry")
            market = getattr(req, 'market', '') or os.getenv("MARKET", "FSI")
            question = getattr(req, 'question', '') or ""
            customer = getattr(req, 'customer', '') or ""
            competitor = getattr(req, 'competitor', '') or ""
            out_dir = getattr(req, 'out_dir', '') or os.getenv("OUTPUT_DIR", "outputs")
            # filename 처리: 요청에서 가져오거나 환경변수에서 가져오거나 None
            # 1. 요청에서 filename이 있으면 사용 (빈 문자열이 아닌 경우)
            filename = getattr(req, 'filename', '') or None
            if filename and filename.strip():
                filename = filename.strip()
            else:
                # 2. 요청에 없으면 환경변수에서 가져오기
                env_filename = os.getenv("OUTPUT_FILENAME")
                if env_filename and env_filename.strip():
                    filename = env_filename.strip()
                else:
                    filename = None
            
            writer_result = await self._call_writer(
                company, market, question, customer, 
                req.features, revenue_value, competitor, out_dir, filename
            )
            if writer_result.ok:
                # WriterAgent가 최종 파일을 저장함
                return agents_pb2.RevenueModelResponse(ok=True, value=revenue_value)
            else:
                return agents_pb2.RevenueModelResponse(ok=False, error=f"WriterAgent 호출 실패: {writer_result.error}")
        except Exception as e:
            # 실패 응답 반환 (오류 메시지 포함)
            return agents_pb2.RevenueModelResponse(ok=False, error=str(e))


async def serve(port: int = None):
    """gRPC 서버 시작 함수"""
    # 포트 설정: 인자로 전달된 포트 또는 환경변수 또는 기본값 6004
    port = port or int(os.getenv("REVENUE_PORT", "6004"))
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # RevenueService를 서버에 등록
    agents_pb2_grpc.add_RevenueServiceServicer_to_server(
        RevenueService(), server
    )
    # 서버를 지정된 포트에 바인딩 (모든 인터페이스에서 접근 가능)
    server.add_insecure_port(f"0.0.0.0:{port}")
    # 서버 시작
    await server.start()
    print(f"[RevenueService] running {port}")
    # 서버 종료 대기
    await server.wait_for_termination()


# 직접 실행 시 gRPC 서버를 시작하는 진입점
if __name__ == "__main__":
    import argparse
    # 명령줄 인자 파서 생성
    p = argparse.ArgumentParser()
    # 포트 오버라이드 옵션 추가
    p.add_argument("--port", type=int)
    args = p.parse_args()
    # 서버 실행
    asyncio.run(serve(args.port))
