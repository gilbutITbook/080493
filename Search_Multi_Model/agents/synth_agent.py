# agents/synth_agent.py
"""
Synth (Synthesis) Agent 모듈
최고 점수를 받은 후보와 비평 노트를 바탕으로 최종 답변을 합성하는 에이전트입니다.
Anthropic Claude를 사용하여 최종 한국어 답변을 생성합니다.
"""
import os, sys
# 상위 디렉토리를 경로에 추가하여 모듈 import 가능하게 함
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import os
import json
from concurrent import futures

import grpc

from llm_wrappers.anthropic_chat import AnthropicChat

import a2a_pb2
import a2a_pb2_grpc


##########################################
#             Synth Agent
##########################################

class SynthResult:
    """
    Synth 에이전트의 실행 결과를 담는 데이터 클래스
    """
    def __init__(self, text: str, meta: dict):
        """
        Synth 결과 초기화
        
        Args:
            text: 최종 합성된 텍스트
            meta: 메타데이터 (토큰 사용량 등)
        """
        self.text = text
        self.meta = meta


class SynthesizerAgent:
    """
    최종 합성 에이전트
    Scoring에서 선정된 최고 후보와 Critic의 비평 노트를 바탕으로 최종 답변을 생성합니다.
    """

    def __init__(self, llm=None):
        """
        Synthesizer 에이전트 초기화
        
        Args:
            llm: LLM 래퍼 인스턴스 (기본값: AnthropicChat)
        """
        self.llm = llm or AnthropicChat()

    def run(self, task: str, best_candidate: str, notes: list):
        """
        최고 후보와 비평 노트를 바탕으로 최종 답변을 합성합니다.
        
        Args:
            task: 원본 작업 요청
            best_candidate: 최고 점수를 받은 후보 텍스트
            notes: Critic에서 발견된 이슈 요약 노트 리스트
            
        Returns:
            SynthResult: 최종 합성된 텍스트와 메타데이터
        """
        # 비평 노트를 포맷팅하여 하나의 문자열로 결합
        notes_block = "\n".join(f"- {n}" for n in notes)

        # 시스템 프롬프트: 한국어 작성 어시스턴트 역할
        system = "You are a Korean writing assistant."
        # 사용자 프롬프트: 요청, 최고 후보, 비평 노트 포함
        user = f"""
[요청]
{task}

[최고 점수 후보]
{best_candidate}

[비평 노트]
{notes_block}

최종 한국어 답변을 작성.
"""
        # LLM 호출하여 최종 답변 생성
        text, meta = self.llm.complete(system, user)

        # 결과 객체 생성 및 반환
        return SynthResult(text=text, meta=meta)


##########################################
#              gRPC Synth Server
##########################################

class SynthService(a2a_pb2_grpc.SynthServiceServicer):
    """
    gRPC Synth 서비스를 구현하는 클래스
    """
    def __init__(self):
        """
        서비스 초기화 및 에이전트 인스턴스 생성
        """
        self.agent = SynthesizerAgent()

    def RunSynth(self, request, context):
        """
        gRPC RunSynth 메서드 구현
        요청을 받아 Synthesizer 에이전트를 실행하고 결과를 반환합니다.
        
        Args:
            request: SynthRequest (task, best_candidate, notes 포함)
            context: gRPC 컨텍스트
            
        Returns:
            AgentReply: 최종 합성된 텍스트와 메타데이터
        """
        # gRPC 요청의 notes를 리스트로 변환
        notes = list(request.notes)
        # 에이전트 실행
        result = self.agent.run(request.task, request.best_candidate, notes)

        # gRPC 응답 생성
        return a2a_pb2.AgentReply(
            text=result.text,
            meta_json=json.dumps(result.meta, ensure_ascii=False)
        )


def serve():
    """
    gRPC 서버를 시작하고 요청을 대기합니다.
    환경 변수에서 포트를 읽거나 기본값(6004)을 사용합니다.
    """
    # 포트 설정 (환경 변수 또는 기본값)
    port = int(os.getenv("A2A_SYNTH_PORT", "6004"))
    # gRPC 서버 생성 (최대 8개 워커 스레드)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    # Synth 서비스를 서버에 등록
    a2a_pb2_grpc.add_SynthServiceServicer_to_server(SynthService(), server)
    # 포트 바인딩 (IPv6 모든 인터페이스)
    server.add_insecure_port(f"[::]:{port}")
    print(f"[SynthAgent] gRPC server running at {port}")
    # 서버 시작
    server.start()
    # 종료 신호 대기
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
