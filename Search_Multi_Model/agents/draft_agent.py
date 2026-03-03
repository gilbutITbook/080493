# agents/draft_agent.py
"""
Draft Agent 모듈
작업 요청을 받아 초안 텍스트를 생성하는 에이전트입니다.
OpenAI GPT를 사용하여 구조화된 한국어 초안을 작성합니다.
"""
import os, sys
# 상위 디렉토리를 경로에 추가하여 모듈 import 가능하게 함
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import os
import json
from concurrent import futures

import grpc

from llm_wrappers.openai_chat import OpenAIChat
import a2a_pb2
import a2a_pb2_grpc


##########################################
#             Draft Agent
##########################################

class DraftResult:
    """
    Draft 에이전트의 실행 결과를 담는 데이터 클래스
    """
    def __init__(self, text: str, meta: dict):
        """
        Draft 결과 초기화
        
        Args:
            text: 생성된 초안 텍스트
            meta: 메타데이터 (토큰 사용량 등)
        """
        self.text = text
        self.meta = meta


class DraftAgent:
    """
    초안 생성 에이전트
    작업 요청을 받아 구조화된 한국어 초안을 생성하고, Critic Agent를 직접 호출합니다.
    """

    def __init__(self, llm=None, critic_addr: str = None):
        """
        Draft 에이전트 초기화
        
        Args:
            llm: LLM 래퍼 인스턴스 (기본값: OpenAIChat)
            critic_addr: Critic Agent 주소 (기본값: 환경 변수 또는 localhost:6002)
        """
        self.llm = llm or OpenAIChat()
        self.critic_addr = critic_addr or os.getenv("A2A_CRITIC_ADDR", "localhost:6002")

    def _call_critic(self, task: str, draft_text: str) -> dict:
        """
        Critic Agent를 gRPC로 직접 호출합니다.
        
        Args:
            task: 원본 작업 요청
            draft_text: 비평할 초안 텍스트
            
        Returns:
            딕셔너리: {"text": 개선된 텍스트, "meta": 메타데이터}
        """
        with grpc.insecure_channel(self.critic_addr) as ch:
            stub = a2a_pb2_grpc.CriticServiceStub(ch)
            resp = stub.RunCritic(a2a_pb2.CriticRequest(task=task, draft=draft_text))
            meta = json.loads(resp.meta_json or "{}")
            return {"text": resp.text, "meta": meta}

    def run(self, task: str) -> DraftResult:
        """
        작업 요청에 대한 초안을 생성하고, Critic Agent를 직접 호출합니다.
        
        Args:
            task: 초안을 생성할 작업 설명
            
        Returns:
            DraftResult: Critic이 개선한 텍스트와 메타데이터 (체인 결과)
        """
        # 시스템 프롬프트: 명확하고 구조화된 한국어 초안 작성 역할
        system = (
            "You are a writing assistant that generates a clear structured Korean draft."
        )
        # 사용자 프롬프트: 작업 요청
        user = f"다음 요청에 대한 한국어 초안을 작성:\n{task}"

        # LLM 호출하여 초안 생성
        text, meta = self.llm.complete(system, user)

        # Critic Agent를 직접 호출하여 초안 개선
        critic_res = self._call_critic(task, text)
        
        # Critic 결과를 반환 (체인 결과)
        return DraftResult(text=critic_res["text"], meta={**meta, **critic_res["meta"]})


##########################################
#          gRPC Draft Server
##########################################

class DraftService(a2a_pb2_grpc.DraftServiceServicer):
    """
    gRPC Draft 서비스를 구현하는 클래스
    """
    def __init__(self):
        """
        서비스 초기화 및 에이전트 인스턴스 생성
        """
        self.agent = DraftAgent()

    def RunDraft(self, request, context):
        """
        gRPC RunDraft 메서드 구현
        요청을 받아 Draft 에이전트를 실행하고 결과를 반환합니다.
        
        Args:
            request: DraftRequest (task 포함)
            context: gRPC 컨텍스트
            
        Returns:
            AgentReply: 생성된 초안 텍스트와 메타데이터
        """
        # 에이전트 실행
        result = self.agent.run(request.task)
        # gRPC 응답 생성
        return a2a_pb2.AgentReply(
            text=result.text,
            meta_json=json.dumps(result.meta, ensure_ascii=False)
        )


def serve():
    """
    gRPC 서버를 시작하고 요청을 대기합니다.
    환경 변수에서 포트를 읽거나 기본값(6001)을 사용합니다.
    """
    # 포트 설정 (환경 변수 또는 기본값)
    port = int(os.getenv("A2A_DRAFT_PORT", "6001"))
    # gRPC 서버 생성 (최대 8개 워커 스레드)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    # Draft 서비스를 서버에 등록
    a2a_pb2_grpc.add_DraftServiceServicer_to_server(DraftService(), server)
    # 포트 바인딩 (IPv6 모든 인터페이스)
    server.add_insecure_port(f"[::]:{port}")
    print(f"[DraftAgent] gRPC server running at {port}")
    # 서버 시작
    server.start()
    # 종료 신호 대기
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
