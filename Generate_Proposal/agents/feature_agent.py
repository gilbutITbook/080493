# feature_agent.py
# 기능 제안 에이전트 모듈
# 경쟁사 분석과 고객 분석을 바탕으로 차별화된 기능을 제안합니다.
from __future__ import annotations
import os
import grpc
import asyncio

from openai import AsyncOpenAI

import agents_pb2
import agents_pb2_grpc


class FeatureSuggestionAgent:
    """기능 제안을 수행하는 에이전트 클래스"""
    def __init__(self):
        # 환경변수에서 OpenAI API 키를 가져옴
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            # API 키가 있으면 AsyncOpenAI 클라이언트 초기화
            self.client = AsyncOpenAI(api_key=api_key)
        else:
            # API 키가 없으면 None으로 설정 (LLM 없이 동작 가능)
            self.client = None
    
    async def propose(self, competitor: str, customer: str):
        """경쟁사와 고객 분석을 바탕으로 기능 제안"""
        try:
            # LLM이 없으면 기본 메시지 반환
            if not self.client:
                return {
                    "ok": True,
                    "features": f"기능 제안:\n- 경쟁사 분석:\n{competitor}\n\n- 고객 분석:\n{customer}\n\n(LLM 분석을 위해 OPENAI_API_KEY 환경변수를 설정해주세요)"
                }
            
            # 기능 제안을 위한 프롬프트 구성
            # 경쟁사 분석과 고객 분석 결과를 종합하여 차별화된 기능 제안 요청
            prompt = f"""다음 경쟁사 분석과 고객 분석 정보를 바탕으로 Azure AI Foundry의 기능 제안을 작성해주세요.

[경쟁사 분석]
{competitor}

[고객 분석]
{customer}

위 정보를 종합하여 다음을 포함한 기능 제안을 한국어로 작성해주세요:
1. 경쟁사 대비 Azure AI Foundry의 차별화된 기능
2. 고객 니즈에 맞춘 맞춤형 기능 제안
3. 각 기능의 비즈니스 가치 및 ROI
4. 우선순위별 기능 로드맵
5. 고객별 맞춤형 제안 전략

구체적이고 실행 가능한 제안을 제시해주세요."""

            # OpenAI API를 통해 기능 제안 요청
            # gpt-5.2 모델 사용, temperature 0.7로 창의성과 일관성의 균형 유지
            response = await self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "당신은 AI 플랫폼 제품 기획 전문가입니다. 경쟁사 분석과 고객 니즈를 바탕으로 차별화된 기능을 제안합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            
            # 응답에서 기능 제안 내용 추출
            features = response.choices[0].message.content
            
            # 성공 응답 반환
            return {
                "ok": True,
                "features": features
            }
            
        except Exception as e:
            # 예외 발생 시 오류 정보 반환
            return {"ok": False, "error": str(e)}


class FeatureService(agents_pb2_grpc.FeatureServiceServicer):
    """gRPC 서비스 - 기능 제안 서비스 구현"""
    def __init__(self):
        # FeatureSuggestionAgent 인스턴스 생성
        self.agent = FeatureSuggestionAgent()
        # 다음 에이전트 주소 설정
        self.revenue_addr = os.getenv("REVENUE_ADDR", "localhost:6004")

    async def _call_revenue(self, features: str, company: str, market: str, question: str, customer: str, competitor: str, out_dir: str, filename: str | None):
        """RevenueAgent 호출"""
        try:
            async with grpc.aio.insecure_channel(self.revenue_addr) as ch:
                stub = agents_pb2_grpc.RevenueServiceStub(ch)
                return await stub.Model(
                    agents_pb2.RevenueModelRequest(
                        features=features,
                        company=company,
                        market=market,
                        question=question,
                        customer=customer,
                        competitor=competitor,
                        out_dir=out_dir,
                        filename=filename or ""  # None이면 빈 문자열로 변환
                    )
                )
        except Exception as e:
            return agents_pb2.RevenueModelResponse(ok=False, error=str(e))

    async def Propose(self, req, ctx):
        """gRPC Propose 메서드 - 기능 제안 요청 처리"""
        try:
            # 에이전트의 propose 메서드 호출하여 기능 제안 수행
            out = await self.agent.propose(req.competitor, req.customer)
            if not out.get("ok"):
                return agents_pb2.FeatureProposeResponse(ok=False, error=out.get("error", "기능 제안 실패"))
            
            features_value = out["features"]
            
            # RevenueAgent를 직접 호출
            company = getattr(req, 'company', '') or os.getenv("COMPANY", "Azure AI Foundry")
            market = getattr(req, 'market', '') or os.getenv("MARKET", "FSI")
            question = getattr(req, 'question', '') or ""
            out_dir = os.getenv("OUTPUT_DIR", "outputs")
            # filename 처리: 환경변수에서 가져오기
            env_filename = os.getenv("OUTPUT_FILENAME")
            if env_filename and env_filename.strip():
                filename = env_filename.strip()
            else:
                filename = None
            
            revenue_result = await self._call_revenue(
                features_value, company, market, question, 
                req.customer, req.competitor, out_dir, filename
            )
            if revenue_result.ok:
                # RevenueAgent가 다음 에이전트를 호출하도록 처리됨
                return agents_pb2.FeatureProposeResponse(ok=True, value=features_value)
            else:
                return agents_pb2.FeatureProposeResponse(ok=False, error=f"RevenueAgent 호출 실패: {revenue_result.error}")
        except Exception as e:
            # 실패 응답 반환 (오류 메시지 포함)
            return agents_pb2.FeatureProposeResponse(ok=False, error=str(e))


async def serve(port: int = None):
    """gRPC 서버 시작 함수"""
    # 포트 설정: 인자로 전달된 포트 또는 환경변수 또는 기본값 6003
    port = port or int(os.getenv("FEATURE_PORT", "6003"))
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # FeatureService를 서버에 등록
    agents_pb2_grpc.add_FeatureServiceServicer_to_server(
        FeatureService(), server
    )
    # 서버를 지정된 포트에 바인딩 (모든 인터페이스에서 접근 가능)
    server.add_insecure_port(f"0.0.0.0:{port}")
    # 서버 시작
    await server.start()
    print(f"[FeatureService] running {port}")
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
