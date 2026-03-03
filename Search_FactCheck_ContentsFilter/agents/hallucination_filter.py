# 환각 필터 에이전트 모듈
# 응답의 환각 여부를 분석하고, Enhanced Content Filter를 통해 안전성을 검사합니다.

import os, sys
# 상위 디렉토리를 Python 경로에 추가하여 agents_pb2 모듈을 import할 수 있도록 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import grpc
import json
import asyncio
from openai import AsyncOpenAI

import agents_pb2
import agents_pb2_grpc

# Enhanced Content Filter 모듈 import
# 이 모듈은 콘텐츠의 안전성을 검사하는 역할을 합니다
from enhanced_content_filter import EnhancedContentFilter

class HalluService(agents_pb2_grpc.HalluServiceServicer):
    """
    환각 필터 서비스 클래스
    gRPC 서비스로 구현되어 있으며, 응답의 환각 여부와 안전성을 분석합니다.
    """
    def __init__(self, model="gpt-5.2"):
        """서비스 초기화 - OpenAI API 클라이언트, Enhanced Content Filter, Responder 스텁 생성"""
        key = os.getenv("OPENAI_API_KEY")
        # 비동기 OpenAI 클라이언트 생성
        self.client = AsyncOpenAI(api_key=key)
        # 사용할 GPT 모델 지정
        self.model = model
        # Enhanced Content Filter 인스턴스 생성
        # 콘텐츠의 안전성을 검사하기 위해 사용됩니다
        self.enhanced = EnhancedContentFilter(model=model)

        # Responder 서비스에 대한 gRPC 스텁 생성
        # 환각이 감지된 경우 답변을 수정하기 위해 사용됩니다
        self.responder = agents_pb2_grpc.ResponderServiceStub(
            grpc.aio.insecure_channel("localhost:50052")
        )
        
        # Finalizer 서비스에 대한 gRPC 스텁 생성
        # 최종 응답 생성을 위해 사용됩니다
        self.finalizer = agents_pb2_grpc.FinalizerServiceStub(
            grpc.aio.insecure_channel("localhost:50055")
        )

    async def Analyze(self, request, context):
        """
        환각 및 안전성 분석 메서드
        응답과 팩트 데이터를 받아 환각 여부와 안전성을 종합적으로 분석합니다.
        """
        # 요청에서 답변과 팩트 데이터 추출
        answer = request.answer
        facts = request.fact_data

        # 1단계: Enhanced Content Filter를 통해 안전성 검사
        # 위험한 콘텐츠가 감지되면 안전한 대체 응답을 반환합니다
        safe = await self.enhanced.filter_content(answer)
        if safe != answer:
            # 안전하지 않은 콘텐츠가 감지된 경우 즉시 반환
            return agents_pb2.HalluResponse(
                overall_risk="high",
                revised_answer=safe,                    # 안전한 대체 응답
                fact_status=facts.verification_status,  # 팩트 검증 상태
                hallucination_level="unknown"           # 환각 수준은 알 수 없음
            )

        # 2단계: 환각 감지 수행
        # 팩트 데이터와 답변을 비교하여 환각 여부를 판단합니다
        hallu = await self._detect(answer, facts)

        # 3단계: 환각 수준이 높은 경우 답변 수정
        if hallu["hallucination_level"] == "high":
            # Responder 서비스를 호출하여 답변을 더 보수적으로 수정
            revised = await self.responder.Revise(
                agents_pb2.ReviseRequest(
                    answer=answer,
                    reasons="허위 가능성 높음"
                )
            )
            # 수정된 답변 추출
            answer2 = revised.answer
            # 수정된 답변에 대해 다시 환각 감지 수행
            hallu = await self._detect(answer2, facts)
            # 수정된 결과 반환
            return agents_pb2.HalluResponse(
                overall_risk="high",
                revised_answer=answer2,                 # 수정된 답변
                fact_status=facts.verification_status, # 팩트 검증 상태
                hallucination_level=hallu["hallucination_level"]  # 환각 수준
            )

        # 환각 수준이 낮거나 중간인 경우 원본 답변 반환
        return agents_pb2.HalluResponse(
            overall_risk="low",
            revised_answer=answer,                      # 원본 답변 유지
            fact_status=facts.verification_status,     # 팩트 검증 상태
            hallucination_level=hallu["hallucination_level"]  # 환각 수준
        )
    
    async def AnalyzeAndFinalize(self, request, context):
        """
        환각 분석 및 최종 응답 생성 메서드
        Analyze를 수행한 후 Finalizer를 직접 호출하여 최종 응답을 생성합니다.
        에이전트 간 직접 통신을 통해 Finalizer를 호출합니다.
        """
        # Analyze 수행
        hallu_response = await self.Analyze(request, context)
        
        # Finalizer를 직접 호출하여 최종 응답 생성
        final = await self.finalizer.Finalize(
            agents_pb2.FinalizeRequest(
                answer=hallu_response.revised_answer,
                hallu=hallu_response,
                fact_data=request.fact_data
            )
        )
        return final

    async def _detect(self, answer, facts_msg):
        """
        환각 감지 내부 메서드
        GPT를 사용하여 답변과 팩트를 비교하여 환각 여부를 판단합니다.
        """
        # 팩트 메시지에서 콘텐츠만 추출하여 리스트 생성
        fact_list = [
            f.content for f in facts_msg.facts
        ]
        # 팩트 리스트를 텍스트로 결합
        fact_text = "\n".join(fact_list)

        # 환각 감지를 위한 프롬프트 구성
        prompt = f"""
다음 답변이 팩트와 비교했을 때 환각인지 JSON으로만 판단:

[답변]
{answer}

[팩트]
{fact_text}

JSON 스키마:
{{
  "hallucination_level": "low|medium|high"
}}
"""
        try:
            # OpenAI API를 통해 환각 수준 판단
            # temperature=0으로 설정하여 일관된 판단을 보장합니다
            r = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role":"user","content":prompt}],
                temperature=0,
                response_format={"type":"json_object"}  # JSON 형식으로 응답 요청
            )
            # JSON 응답을 파싱하여 반환
            return json.loads(r.choices[0].message.content)
        except:
            # 에러 발생 시 알 수 없음으로 반환
            return {"hallucination_level":"unknown"}

async def serve():
    """
    gRPC 서버 실행 함수
    환각 필터 서비스를 gRPC 서버로 실행합니다.
    """
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # HalluService를 서버에 등록
    agents_pb2_grpc.add_HalluServiceServicer_to_server(
        HalluService(), server
    )
    # 포트 50054에서 서비스 시작 (모든 인터페이스에서 수신)
    server.add_insecure_port("[::]:50054")
    await server.start()
    print("HalluService ON 50054")
    # 서버 종료 대기
    await server.wait_for_termination()

if __name__ == "__main__":
    # 직접 실행 시 서버 시작
    asyncio.run(serve())
