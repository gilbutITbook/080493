# orchestrator.py
"""
A2A (Agent-to-Agent) 오케스트레이션 시스템

Draft / Critic / Scoring / Synth 에이전트를
각각의 gRPC 서버로 호출하여 파이프라인을 구성합니다.
"""

import os
import re
import json
from typing import Dict, Any, Optional

import grpc

import a2a_pb2
import a2a_pb2_grpc
from metrics import PerformanceMonitor


class Orchestrator:
    """
    A2A 오케스트레이터 클래스

    각 에이전트는 별도 포트에서 gRPC 서버로 동작하며,
    이 클래스는 해당 엔드포인트를 호출하여 전체 파이프라인을 수행합니다.
    """

    def __init__(
        self,
        draft_addr: Optional[str] = None,
    ):
        """
        오케스트레이터 초기화

        Args:
            draft_addr: DraftService 엔드포인트 (host:port)
        """
        self.draft_addr = draft_addr or os.getenv("A2A_DRAFT_ADDR", "localhost:6001")
        self.performance_monitor = PerformanceMonitor()

    # ---------------- gRPC 호출 헬퍼 ----------------

    def _call_draft(self, task: str) -> Dict[str, Any]:
        """
        Draft 에이전트를 gRPC로 호출하여 초안을 생성합니다.
        
        Args:
            task: 초안을 생성할 작업 설명
            
        Returns:
            딕셔너리: {"text": 초안 텍스트, "meta": 메타데이터}
            
        Raises:
            Exception: gRPC 호출 실패 시
        """
        # 성능 모니터링 시작
        t0 = self.performance_monitor.start_timer("Draft")
        try:
            # gRPC 채널 생성 (비보안 연결)
            with grpc.insecure_channel(self.draft_addr) as ch:
                # Draft 서비스 스텁 생성
                stub = a2a_pb2_grpc.DraftServiceStub(ch)
                # Draft 요청 전송 및 응답 수신
                resp = stub.RunDraft(a2a_pb2.DraftRequest(task=task))
            # 메타데이터 JSON 파싱
            meta = json.loads(resp.meta_json or "{}")
            # 성능 메트릭 기록 (토큰 사용량, 비용 추정 포함)
            self.performance_monitor.record_metrics(
                "Draft",
                t0,
                token_usage=meta.get("token_usage"),
                cost_estimate=meta.get("cost_estimate", 0.0),
            )
            # 결과 반환
            return {"text": resp.text, "meta": meta}
        except Exception as e:
            # 에러 발생 시 실패 메트릭 기록
            self.performance_monitor.record_metrics(
                "Draft", t0, success=False, error_message=str(e)
            )
            raise

    def _safety_pass(self, text: str) -> str:
        """
        텍스트에서 민감한 정보(API 키 등)를 제거하는 보안 필터링 함수
        
        Args:
            text: 필터링할 텍스트
            
        Returns:
            민감한 정보가 제거된 텍스트
        """
        # OpenAI 스타일 API 키 패턴 제거 (sk-로 시작하는 긴 문자열)
        text = re.sub(r"(sk-[A-Za-z0-9\-_]{20,})", "[REDACTED-KEY]", text)
        # API 키 할당 패턴 제거 (api_key="..." 또는 api-key='...' 형식)
        text = re.sub(
            r'(?i)(api[_-]?key)\s*=\s*["\'][^"\']+["\']', r'\1="[REDACTED]"', text
        )
        return text

    # ---------------- 메인 파이프라인 ----------------

    def run(self, task: str, debug: bool = False) -> Dict[str, Any]:
        """
        A2A 파이프라인 실행:
        Draft(OpenAI) → Critic(Claude) → Score(OpenAI) → Synthesis(Claude)
        
        에이전트 간 직접 통신으로 처리되므로, Orchestrator는 Draft만 호출합니다.
        """
        # Draft: OpenAI를 사용하여 초안 생성
        # Draft Agent가 자동으로 Critic → Scoring → Synth를 호출합니다.
        draft_res = self._call_draft(task)
        final_text = draft_res["text"]
        final_meta = draft_res["meta"]

        # 보안 필터링: API 키 등 민감한 정보 제거
        final_text = self._safety_pass(final_text)

        # 결과 딕셔너리 구성
        result: Dict[str, Any] = {
            "final": final_text,
        }

        # 디버그 모드인 경우 상세 추적 정보 추가
        if debug:
            result["trace"] = {
                "meta": final_meta,
            }

        return result
