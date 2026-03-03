# 질문 정제 에이전트 모듈
# 사용자의 질문을 핵심 정보 중심으로 단순화하고 불필요한 표현을 제거합니다.

import os, sys
# 상위 디렉토리를 Python 경로에 추가하여 agents_pb2 모듈을 import할 수 있도록 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import grpc
from openai import AsyncOpenAI

import agents_pb2
import agents_pb2_grpc

class RefinerService(agents_pb2_grpc.RefinerServiceServicer):
    """
    질문 정제 서비스 클래스
    gRPC 서비스로 구현되어 있으며, 사용자 질문을 정제하는 역할을 담당합니다.
    """
    def __init__(self, model="gpt-5.2"):
        """서비스 초기화 - OpenAI API 키 검증 및 클라이언트 생성"""
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set")
        # 비동기 OpenAI 클라이언트 생성
        self.client = AsyncOpenAI(api_key=key)
        # 사용할 GPT 모델 지정
        self.model = model
        
        # 다른 에이전트 서비스에 대한 gRPC 스텁 생성
        # 에이전트 간 직접 통신을 위해 사용됩니다
        self.responder = agents_pb2_grpc.ResponderServiceStub(
            grpc.aio.insecure_channel("localhost:50052")
        )
        self.fact_checker = agents_pb2_grpc.FactCheckerServiceStub(
            grpc.aio.insecure_channel("localhost:50053")
        )
        self.hallu = agents_pb2_grpc.HalluServiceStub(
            grpc.aio.insecure_channel("localhost:50054")
        )

    async def Process(self, request, context):
        """
        전체 파이프라인 처리 메서드
        질문 정제부터 최종 응답 생성까지 전체 파이프라인을 실행합니다.
        에이전트 간 직접 통신을 통해 처리됩니다.
        """
        # 1단계: 질문 정제
        refined_q = request.user_question.strip()
        prompt = f"다음 질문을 핵심만 간결하게 정제:\n{refined_q}"
        r = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        refined = r.choices[0].message.content.strip()
        
        # 2단계: Responder와 FactChecker를 병렬로 호출
        ans_task = self.responder.Answer(
            agents_pb2.AnswerRequest(refined=refined)
        )
        fact_task = self.fact_checker.Check(
            agents_pb2.FactCheckRequest(refined=refined)
        )
        
        # 병렬 작업 완료 대기
        answer, facts = await asyncio.gather(ans_task, fact_task)
        
        # 3단계: HalluService의 AnalyzeAndFinalize를 호출
        # 이 메서드는 내부에서 Finalizer를 호출하여 최종 응답을 생성합니다
        final = await self.hallu.AnalyzeAndFinalize(
            agents_pb2.HalluRequest(answer=answer.answer, fact_data=facts)
        )
        
        return final

async def serve():
    """
    gRPC 서버 실행 함수
    질문 정제 서비스를 gRPC 서버로 실행합니다.
    """
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # RefinerService를 서버에 등록
    agents_pb2_grpc.add_RefinerServiceServicer_to_server(
        RefinerService(), server
    )
    # 포트 50051에서 서비스 시작 (모든 인터페이스에서 수신)
    server.add_insecure_port("[::]:50051")
    await server.start()
    print("RefinerService ON 50051")
    # 서버 종료 대기
    await server.wait_for_termination()

if __name__ == "__main__":
    # 직접 실행 시 서버 시작
    asyncio.run(serve())
