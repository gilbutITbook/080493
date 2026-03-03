# 응답 생성 에이전트 모듈
# 정제된 질문을 받아 사실 기반의 초안 응답을 생성하고, 필요 시 답변을 수정합니다.

import os, sys
# 상위 디렉토리를 Python 경로에 추가하여 agents_pb2 모듈을 import할 수 있도록 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import grpc
from openai import AsyncOpenAI

import agents_pb2
import agents_pb2_grpc

class ResponderService(agents_pb2_grpc.ResponderServiceServicer):
    """
    응답 생성 서비스 클래스
    gRPC 서비스로 구현되어 있으며, 질문에 대한 답변을 생성하고 수정하는 역할을 담당합니다.
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

    async def Answer(self, request, context):
        """
        초안 답변 생성 메서드
        정제된 질문을 받아 사실 기반의 초안 응답을 생성합니다.
        """
        # 정제된 질문 추출 및 공백 제거
        refined = request.refined.strip()
        # 사실 기반 답변 생성을 위한 프롬프트 구성
        prompt = f"질문: {refined}\n사실 기반으로 답변하세요."
        # OpenAI API를 통해 답변 생성
        # temperature=0.3으로 설정하여 적절한 창의성과 안정성의 균형을 유지합니다
        r = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        # 생성된 답변 추출 및 공백 제거
        answer = r.choices[0].message.content.strip()
        # gRPC 응답 반환
        return agents_pb2.AnswerResponse(answer=answer)

    async def Revise(self, request, context):
        """
        답변 수정 메서드
        환각 필터에서 문제가 감지된 경우 답변을 더 보수적으로 수정합니다.
        """
        # 원본 답변과 수정 사유 추출
        base = request.answer
        reasons = request.reasons
        # 답변 수정을 위한 프롬프트 구성
        prompt = f"{base}\n\n[검토사유]\n{reasons}\n\n더 보수적으로 수정."
        # OpenAI API를 통해 답변 수정
        # temperature=0으로 설정하여 일관되고 보수적인 수정을 보장합니다
        r = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        # 수정된 답변 추출 및 공백 제거
        revised = r.choices[0].message.content.strip()
        # gRPC 응답 반환
        return agents_pb2.AnswerResponse(answer=revised)

async def serve():
    """
    gRPC 서버 실행 함수
    응답 생성 서비스를 gRPC 서버로 실행합니다.
    """
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # ResponderService를 서버에 등록
    agents_pb2_grpc.add_ResponderServiceServicer_to_server(
        ResponderService(), server
    )
    # 포트 50052에서 서비스 시작 (모든 인터페이스에서 수신)
    server.add_insecure_port("[::]:50052")
    await server.start()
    print("ResponderService ON 50052")
    # 서버 종료 대기
    await server.wait_for_termination()

if __name__ == "__main__":
    # 직접 실행 시 서버 시작
    asyncio.run(serve())
