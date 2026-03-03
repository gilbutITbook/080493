# agents/critic_agent.py
"""
Critic Agent 모듈
초안 텍스트를 비평하고 개선된 버전을 생성하는 에이전트입니다.
Anthropic Claude를 사용하여 한국어 텍스트를 검토합니다.
"""
import os, sys
# 상위 디렉토리를 경로에 추가하여 모듈 import 가능하게 함
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import os
import json
from concurrent import futures

import grpc

from llm_wrappers.anthropic_chat import AnthropicChat
from json_utils import safe_json_loads

import a2a_pb2
import a2a_pb2_grpc


##########################################
#             Critic Agent
##########################################

class CriticResult:
    """
    Critic 에이전트의 실행 결과를 담는 데이터 클래스
    """
    def __init__(self, text: str, issues: list, meta: dict):
        """
        Critic 결과 초기화
        
        Args:
            text: 개선된 텍스트
            issues: 발견된 문제점 리스트
            meta: 메타데이터 (토큰 사용량 등)
        """
        self.text = text
        self.issues = issues
        self.meta = meta


class CriticAgent:
    """
    초안 비평 에이전트
    Draft 에이전트가 생성한 초안을 검토하고 개선 사항을 제안하며, Scoring Agent를 직접 호출합니다.
    """

    def __init__(self, llm=None, scoring_addr: str = None):
        """
        Critic 에이전트 초기화
        
        Args:
            llm: LLM 래퍼 인스턴스 (기본값: AnthropicChat)
            scoring_addr: Scoring Agent 주소 (기본값: 환경 변수 또는 localhost:6003)
        """
        self.llm = llm or AnthropicChat()
        self.scoring_addr = scoring_addr or os.getenv("A2A_SCORING_ADDR", "localhost:6003")

    def _call_scoring(self, task: str, candidates: dict) -> dict:
        """
        Scoring Agent를 gRPC로 직접 호출합니다.
        
        Args:
            task: 원본 작업 요청
            candidates: 평가할 후보 딕셔너리
            
        Returns:
            딕셔너리: {"text": Synth 결과 텍스트, "meta": 메타데이터}
        """
        with grpc.insecure_channel(self.scoring_addr) as ch:
            stub = a2a_pb2_grpc.ScoringServiceStub(ch)
            req = a2a_pb2.ScoringRequest(task=task, candidates=candidates)
            resp = stub.RunScoring(req)
            meta = json.loads(resp.meta_json or "{}")
            return {"text": resp.text, "meta": meta}

    def run(self, task: str, draft: str) -> CriticResult:
        """
        초안을 비평하고 개선된 버전을 생성한 후, Scoring Agent를 직접 호출합니다.
        
        Args:
            task: 원본 작업 요청
            draft: 비평할 초안 텍스트
            
        Returns:
            CriticResult: Scoring 결과 (체인 결과)
        """
        # 시스템 프롬프트: 엄격한 한국어 비평가 역할
        system = (
            "You are a strict Korean writing critic. Return only JSON."
        )
        # 사용자 프롬프트: 요청과 초안을 포함한 비평 요청
        user = f"""
[요청]
{task}

[초안]
{draft}

반환 형식:
{{
  "issues": ["문제1", "문제2"],
  "revised": "개선된 텍스트"
}}
"""

        # LLM 호출하여 비평 및 개선안 생성
        text, meta = self.llm.complete(system, user)

        # JSON 파싱 시도, 실패 시 기본값 사용
        data = safe_json_loads(text) or {"issues": ["JSON 파싱 실패"], "revised": draft}
        revised_text = data.get("revised", draft)
        issues = data.get("issues", [])

        # Draft와 Critic 후보를 Scoring Agent에 전달
        candidates = {"Draft": draft, "Critic": revised_text}
        scoring_res = self._call_scoring(task, candidates)
        
        # Scoring 결과를 반환 (체인 결과)
        return CriticResult(
            text=scoring_res["text"],
            issues=issues,
            meta={**meta, **scoring_res["meta"]}
        )


##########################################
#            gRPC Critic Server
##########################################

class CriticService(a2a_pb2_grpc.CriticServiceServicer):
    """
    gRPC Critic 서비스를 구현하는 클래스
    """
    def __init__(self):
        """
        서비스 초기화 및 에이전트 인스턴스 생성
        """
        self.agent = CriticAgent()

    def RunCritic(self, request, context):
        """
        gRPC RunCritic 메서드 구현
        요청을 받아 Critic 에이전트를 실행하고 결과를 반환합니다.
        (체인 결과: Scoring까지 실행된 결과)
        
        Args:
            request: CriticRequest (task, draft 포함)
            context: gRPC 컨텍스트
            
        Returns:
            AgentReply: Synth 결과 (체인 결과)
        """
        # 에이전트 실행 (체인 결과 반환)
        result = self.agent.run(request.task, request.draft)
        # 메타데이터에 이슈 정보 추가
        output = {
            "issues": result.issues,
            **result.meta
        }
        # gRPC 응답 생성
        return a2a_pb2.AgentReply(
            text=result.text,
            meta_json=json.dumps(output, ensure_ascii=False)
        )


def serve():
    """
    gRPC 서버를 시작하고 요청을 대기합니다.
    환경 변수에서 포트를 읽거나 기본값(6002)을 사용합니다.
    """
    # 포트 설정 (환경 변수 또는 기본값)
    port = int(os.getenv("A2A_CRITIC_PORT", "6002"))
    # gRPC 서버 생성 (최대 8개 워커 스레드)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    # Critic 서비스를 서버에 등록
    a2a_pb2_grpc.add_CriticServiceServicer_to_server(CriticService(), server)
    # 포트 바인딩 (IPv6 모든 인터페이스)
    server.add_insecure_port(f"[::]:{port}")
    print(f"[CriticAgent] gRPC server running at {port}")
    # 서버 시작
    server.start()
    # 종료 신호 대기
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
