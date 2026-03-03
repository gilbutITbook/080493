# agents/scoring_agent.py
"""
Scoring Agent 모듈
여러 후보 초안을 평가하고 점수를 매기는 에이전트입니다.
OpenAI를 사용하여 각 후보의 명확성, 사실성, 완전성을 평가합니다.
"""
import os, sys
# 상위 디렉토리를 경로에 추가하여 모듈 import 가능하게 함
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import os
import json
from concurrent import futures

import grpc

from llm_wrappers.openai_chat import OpenAIChat
from json_utils import safe_json_loads

import a2a_pb2
import a2a_pb2_grpc


##########################################
#             Scoring Agent
##########################################

class ScoringResult:
    """
    Scoring 에이전트의 실행 결과를 담는 데이터 클래스
    """
    def __init__(self, raw: str, parsed: dict, meta: dict):
        """
        Scoring 결과 초기화
        
        Args:
            raw: LLM의 원본 응답 텍스트
            parsed: 파싱된 점수 딕셔너리
            meta: 메타데이터 (토큰 사용량 등)
        """
        self.raw = raw
        self.parsed = parsed
        self.meta = meta


class ScoringAgent:
    """
    여러 후보 초안 점수 평가
    Draft와 Critic이 생성한 후보들을 비교 평가하여 점수를 매기고, Synth Agent를 직접 호출합니다.
    """

    def __init__(self, llm=None, synth_addr: str = None, weights: dict = None):
        """
        Scoring 에이전트 초기화
        
        Args:
            llm: LLM 래퍼 인스턴스 (기본값: OpenAIChat)
            synth_addr: Synth Agent 주소 (기본값: 환경 변수 또는 localhost:6004)
            weights: 점수 가중치 (기본값: {"clarity": 0.3, "factuality": 0.4, "completeness": 0.3})
        """
        self.llm = llm or OpenAIChat()
        self.synth_addr = synth_addr or os.getenv("A2A_SYNTH_ADDR", "localhost:6004")
        self.weights = weights or {"clarity": 0.3, "factuality": 0.4, "completeness": 0.3}

    def _pick_best(self, scores_json: dict, fallback: str) -> str:
        """
        점수 딕셔너리에서 최고 점수를 받은 후보 ID를 선택합니다.
        
        Args:
            scores_json: 점수 정보가 담긴 딕셔너리 ({"scores": [...]} 형식)
            fallback: 점수 파싱 실패 시 반환할 기본값
            
        Returns:
            최고 점수 후보 ID 또는 fallback 값
        """
        try:
            best_id = None
            best_overall = -1.0

            for s in scores_json.get("scores", []):
                overall = s.get("overall")
                if overall is None:
                    overall = (
                        s.get("clarity", 0) * self.weights["clarity"]
                        + s.get("factuality", 0) * self.weights["factuality"]
                        + s.get("completeness", 0) * self.weights["completeness"]
                    )
                if overall > best_overall:
                    best_overall = overall
                    best_id = s.get("id")

            return best_id or fallback
        except Exception:
            return fallback

    def _call_synth(self, task: str, best_candidate: str, notes: list) -> dict:
        """
        Synth Agent를 gRPC로 직접 호출합니다.
        
        Args:
            task: 원본 작업 요청
            best_candidate: 최고 점수를 받은 후보 텍스트
            notes: Critic에서 발견된 이슈 요약 노트 리스트
            
        Returns:
            딕셔너리: {"text": 최종 합성 텍스트, "meta": 메타데이터}
        """
        with grpc.insecure_channel(self.synth_addr) as ch:
            stub = a2a_pb2_grpc.SynthServiceStub(ch)
            req = a2a_pb2.SynthRequest(
                task=task,
                best_candidate=best_candidate,
                notes=notes,
            )
            resp = stub.RunSynth(req)
            meta = json.loads(resp.meta_json or "{}")
            return {"text": resp.text, "meta": meta}

    def run(self, task: str, candidates: dict, critic_issues: list = None) -> ScoringResult:
        """
        여러 후보 초안을 평가하고 점수를 매긴 후, Synth Agent를 직접 호출합니다.
        
        Args:
            task: 원본 작업 요청
            candidates: 후보 딕셔너리 (예: {"Draft": "...", "Critic": "..."})
            critic_issues: Critic에서 발견된 이슈 리스트 (선택적)
            
        Returns:
            ScoringResult: Synth 결과 (체인 결과)
        """
        # 후보들을 포맷팅하여 하나의 문자열로 결합
        formatted = "\n\n".join(f"[{cid}]\n{txt}" for cid, txt in candidates.items())

        # 시스템 프롬프트: JSON 형식으로 점수만 반환
        system = "Return only JSON with scoring."
        # 사용자 프롬프트: 요청과 후보 답변들
        user = f"""
[요청]
{task}

[후보 답변]
{formatted}

JSON만 출력:
{{ "scores": [{{"id":"A","clarity":8,"overall":0.85}}] }}
"""

        # LLM 호출하여 점수 평가
        raw, meta = self.llm.complete(system, user)
        # JSON 파싱 시도, 실패 시 빈 딕셔너리
        parsed = safe_json_loads(raw) or {}

        # 최고 점수 후보 선택
        best_id = self._pick_best(parsed, fallback="Critic")
        best_text = candidates.get(best_id, candidates.get("Critic", ""))

        # Critic 이슈를 노트로 변환
        notes = []
        if critic_issues:
            issues = [i for i in critic_issues if isinstance(i, str)]
            if issues:
                notes.append("리뷰 이슈 요약: " + "; ".join(issues[:6]))

        # Synth Agent를 직접 호출
        synth_res = self._call_synth(task, best_text, notes)
        
        # Synth 결과를 반환 (체인 결과)
        return ScoringResult(
            raw=synth_res["text"],
            parsed={"best_candidate": best_id, **parsed},
            meta={**meta, **synth_res["meta"]}
        )


##########################################
#            gRPC Scoring Server
##########################################

class ScoringService(a2a_pb2_grpc.ScoringServiceServicer):
    """
    gRPC Scoring 서비스를 구현하는 클래스
    """
    def __init__(self):
        """
        서비스 초기화 및 에이전트 인스턴스 생성
        """
        self.agent = ScoringAgent()

    def RunScoring(self, request, context):
        """
        gRPC RunScoring 메서드 구현
        요청을 받아 Scoring 에이전트를 실행하고 결과를 반환합니다.
        (체인 결과: Synth까지 실행된 결과)
        
        Args:
            request: ScoringRequest (task, candidates 포함)
            context: gRPC 컨텍스트
            
        Returns:
            AgentReply: Synth 결과 (체인 결과)
        """
        # gRPC 요청의 candidates를 딕셔너리로 변환
        candidates = dict(request.candidates)
        # 에이전트 실행 (체인 결과 반환)
        # critic_issues는 직접 호출 시 전달되므로 여기서는 None
        result = self.agent.run(request.task, candidates, critic_issues=None)

        # 메타데이터에 파싱된 점수 포함하여 응답 생성
        return a2a_pb2.AgentReply(
            text=result.raw,
            meta_json=json.dumps(
                {"parsed": result.parsed, **result.meta},
                ensure_ascii=False
            )
        )


def serve():
    """
    gRPC 서버를 시작하고 요청을 대기합니다.
    환경 변수에서 포트를 읽거나 기본값(6003)을 사용합니다.
    """
    # 포트 설정 (환경 변수 또는 기본값)
    port = int(os.getenv("A2A_SCORING_PORT", "6003"))
    # gRPC 서버 생성 (최대 8개 워커 스레드)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    # Scoring 서비스를 서버에 등록
    a2a_pb2_grpc.add_ScoringServiceServicer_to_server(ScoringService(), server)
    # 포트 바인딩 (IPv6 모든 인터페이스)
    server.add_insecure_port(f"[::]:{port}")
    print(f"[ScoringAgent] gRPC server running at {port}")
    # 서버 시작
    server.start()
    # 종료 신호 대기
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
