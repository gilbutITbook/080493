# ================================================
# File: improver.py
# Role: 정책 개선안 에이전트 + gRPC 서버 
# Port (default bind): 0.0.0.0:6006
# ================================================

# ============ 표준 라이브러리 및 타입 힌트 ============
# Python 3.7+ 호환성을 위한 annotations 가져오기
from __future__ import annotations

# 운영체제 관련 기능 (환경변수 읽기 등)
import os
# 비동기 프로그래밍 지원
import asyncio
# 데이터 클래스 정의 (타입 안전한 구조체)
from dataclasses import dataclass

# ============ Protocol Buffers 생성 파일 임포트 ============
# voc.proto 파일로부터 생성된 메시지 및 서비스 정의
import grpc
import voc_pb2
import voc_pb2_grpc

# ============ 프로젝트 내부 모듈 임포트 ============
# Anthropic Chat API를 사용하기 위한 래퍼 클래스
from llm_wrappers.anthropic_chat import AnthropicChat
# JSON 파싱 유틸리티 함수
from utils.json_utils import safe_json_loads
# JSON 데이터 처리
import json


# ============ 비즈니스 로직 ============
# 요약된 VOC 내용을 기반으로 정책 개선안을 생성하는 에이전트
# --------------------------------
# 비즈니스 로직
# --------------------------------

# ============ 정책 결과 데이터 클래스 ============
@dataclass
class PolicyResult:
    """
    정책 개선안 생성 결과를 담는 데이터 클래스입니다.
    """
    policy: str  # 생성된 정책 개선안 텍스트


# ============ 정책 개선 에이전트 클래스 ============
class PolicyImproverAgent:
    """
    요약된 VOC 내용을 기반으로 정책 개선안을 생성하고,
    Critic의 수정 지침에 따라 리파인하는 에이전트
    """

    # ============ 초기화 메서드 ============
    def __init__(self, model: str | None = None):
        """
        PolicyImproverAgent 인스턴스를 초기화합니다.
        
        Args:
            model: 사용할 Anthropic 모델명 (None이면 환경변수 또는 기본값 사용)
            
        Raises:
            RuntimeError: Anthropic 클라이언트가 설정되지 않았을 때
        """
        # ============ LLM 래퍼 인스턴스 생성 ============
        # Anthropic Chat 래퍼를 인스턴스 변수로 생성합니다
        # 반드시 인스턴스 생성!! (클래스 변수가 아닌 인스턴스 변수)
        self.llm = AnthropicChat(model=model)
        # 다른 에이전트 엔드포인트 설정
        self.critic_endpoint = os.environ.get("CRITIC_ENDPOINT", "localhost:6005")

    # ============ 정책 개선안 생성 메서드 ============
    async def improve(self, summary: str) -> PolicyResult:
        """
        요약을 기반으로 최초 정책 개선안을 생성합니다.
        
        VOC 요약 내용을 분석하여 실행 가능한 정책 개선안을 제안합니다.
        정책 개선안은 구체적이고 측정 가능하며 우선순위가 명확해야 합니다.
        
        Args:
            summary: VOC 요약 텍스트
            
        Returns:
            PolicyResult: 생성된 정책 개선안을 담은 결과 객체
        """
        # ============ 요약 검증 ============
        # 요약이 비어있거나 너무 짧으면 정책 생성이 어렵습니다
        summary = (summary or "").strip()
        if not summary or len(summary) < 10:
            return PolicyResult(
                policy="요약 내용이 비어 있거나 충분하지 않아 구체적인 정책 개선안을 제안하기 어렵습니다. "
                       "고객 VOC 요약을 제공해 주시면, 그에 기반한 실행 가능하고 우선순위가 명확한 정책 개선안을 제안해 드리겠습니다."
            )
        
        # ============ 프롬프트 구성 ============
        # LLM에게 요약을 기반으로 정책 개선안을 생성하도록 지시하는 프롬프트를 작성합니다
        prompt = f"""
당신은 고객 VOC를 기반으로 정책 개선안을 제안하는 전문가입니다.

다음 요약을 보고, 실행 가능한 정책 개선안을 제안해라.
- 구체적이고 측정 가능하게
- 우선순위가 드러나게
- 담당 조직, 무엇을, 언제까지, 어떻게의 형식으로 작성

[요약]
{summary}

정책 개선안만 깔끔한 한국어 문장으로 출력해라. 요약 내용을 반드시 반영하여 구체적인 정책 개선안을 제시해라.
"""

        # ============ LLM 래퍼를 통한 API 호출 ============
        # Anthropic Chat 래퍼를 사용하여 정책 개선안을 생성합니다
        text = await self.llm(prompt.strip(), max_tokens=1024)

        # ============ 결과 검증 ============
        # 생성된 정책이 비어있거나 너무 짧으면 에러 메시지 반환
        policy_text = (text or "").strip()
        if not policy_text or len(policy_text) < 20:
            return PolicyResult(
                policy="요약 내용을 기반으로 정책 개선안을 생성하려고 시도했으나, 충분한 내용을 생성하지 못했습니다. "
                       "요약 내용을 확인하고 다시 시도해 주세요."
            )

        # ============ 결과 반환 ============
        # 생성된 정책 개선안을 PolicyResult 객체로 감싸서 반환합니다
        return PolicyResult(policy=policy_text)

    # ============ 정책 개선안 개선 메서드 ============
    async def refine(self, policy: str, edits_json: str | None = None) -> PolicyResult:
        """
        Critic의 edits 지침을 반영하여 정책 개선안을 리파인합니다.
        
        Critic이 정책 개선안의 품질을 검토하고 수정 지침을 제공하면,
        이 메서드를 사용하여 원본 정책 개선안을 개선합니다.
        
        Args:
            policy: 개선할 원본 정책 개선안 텍스트
            edits_json: Critic이 제공한 수정 지침 (JSON 문자열, None 가능)
            
        Returns:
            PolicyResult: 개선된 정책 개선안을 담은 결과 객체
        """
        # ============ 수정 지침 파싱 ============
        # JSON 문자열에서 수정 지침 리스트를 추출합니다
        edits = []
        if edits_json:
            # JSON을 안전하게 파싱합니다
            data = safe_json_loads(edits_json) or {}
            edits = data.get("edits") or []
            # 리스트가 아니면 빈 리스트로 변환합니다
            if not isinstance(edits, list):
                edits = []

        # ============ 수정 지침 포맷팅 ============
        # 수정 지침을 프롬프트에 포함할 수 있는 형식으로 변환합니다
        # 지침이 있으면 각 지침을 "- " 접두사와 함께 나열하고,
        # 없으면 일반적인 개선 지침을 사용합니다
        inst = "\n".join(f"- {e}" for e in edits) if edits else "전반적인 표현과 구조를 개선해라."

        # ============ 프롬프트 구성 ============
        # 원본 정책 개선안과 수정 지침을 포함한 프롬프트를 작성합니다
        prompt = f"""
다음 정책 개선안을 아래 수정 지침에 따라 다시 작성해라.

[기존 정책 개선안]
{policy}

[수정 지침]
{inst}

수정된 정책 개선안만 출력해라.
"""

        # ============ LLM 래퍼를 통한 API 호출 ============
        # Anthropic Chat 래퍼를 사용하여 정책 개선안을 개선합니다
        text = await self.llm(prompt.strip(), max_tokens=1024)

        # ============ 결과 검증 ============
        # 개선된 정책이 비어있거나 너무 짧으면 원본 정책 반환
        policy_text = (text or "").strip()
        if not policy_text or len(policy_text) < 20:
            # 원본 정책이 있으면 그대로 반환, 없으면 에러 메시지
            if policy and len(policy.strip()) > 0:
                return PolicyResult(policy=policy.strip())
            else:
                return PolicyResult(
                    policy="정책 개선안을 개선하려고 시도했으나, 충분한 내용을 생성하지 못했습니다."
                )

        # ============ 결과 반환 ============
        # 개선된 정책 개선안을 PolicyResult 객체로 감싸서 반환합니다
        return PolicyResult(policy=policy_text)

    # ============ 정책 생성 파이프라인 실행 메서드 ============
    async def run_policy_pipeline(
        self,
        summary: str,
        timeout: float = 180.0,
    ) -> dict:
        """
        정책 개선안 생성 전체 파이프라인을 실행합니다.
        Critic을 직접 호출하여 정책을 검토하고 개선합니다.
        
        Args:
            summary: VOC 요약 텍스트
            timeout: gRPC 호출 타임아웃
            
        Returns:
            dict: 정책 개선안 결과 및 추적 정보
        """
        trace = []
        
        # ============ 1단계: 정책 개선안 생성 ============
        result = await self.improve(summary)
        policy = result.policy
        trace.append("policy_created")
        
        # ============ 2단계: Critic 호출 ============
        async with grpc.aio.insecure_channel(self.critic_endpoint) as ch:
            stub = voc_pb2_grpc.CriticStub(ch)
            cres = await stub.Review(
                voc_pb2.ReviewReq(
                    doc=policy,
                    role="policy"
                ),
                timeout=timeout
            )
        
        # ============ 3단계: 필요시 정책 개선 ============
        if cres.need_refine and cres.edits:
            result = await self.refine(
                policy,
                json.dumps({"edits": list(cres.edits)}, ensure_ascii=False)
            )
            policy = result.policy
            trace.append("policy_refined")
        
        return {
            "policy": policy,
            "trace": "; ".join(trace),
            "ok": True,
        }


# ============ gRPC 서비스 구현 ============
# Protocol Buffers로 정의된 서비스를 구현하는 클래스
# 클라이언트의 RPC 요청을 받아 PolicyImproverAgent의 비즈니스 로직을 실행합니다
# --------------------------------
# gRPC Servicer
# --------------------------------

class ImproverServicer(voc_pb2_grpc.ImproverServicer):
    """
    Improver gRPC 서비스를 구현하는 클래스입니다.
    
    voc_pb2_grpc.ImproverServicer를 상속받아
    Protocol Buffers로 정의된 RPC 메서드들을 구현합니다.
    """
    # ============ 초기화 메서드 ============
    def __init__(self):
        """
        ImproverServicer 인스턴스를 초기화합니다.
        비즈니스 로직을 담당하는 PolicyImproverAgent를 생성합니다.
        """
        self.imp = PolicyImproverAgent()

    # ============ Improve RPC 구현 ============
    async def Improve(self, request, context):
        """
        Improve RPC를 구현합니다.
        
        클라이언트로부터 요약 텍스트를 받아 정책 개선안을 생성하고,
        Critic을 직접 호출하여 다음 단계로 진행합니다.
        
        Args:
            request: PolicyReq 메시지 (summary 포함)
            context: gRPC 서비스 컨텍스트 (에러 처리 등에 사용)
            
        Returns:
            PolicyRes: 생성된 정책 개선안을 포함한 응답 메시지
        """
        try:
            # ============ 정책 개선안 생성 ============
            # 에이전트의 improve 메서드를 호출하여 정책 개선안을 생성합니다
            result: PolicyResult = await self.imp.improve(request.summary)
            
            # ============ Critic 직접 호출 ============
            # Improver가 Critic을 직접 호출하여 다음 단계로 진행합니다
            async with grpc.aio.insecure_channel(self.imp.critic_endpoint) as ch:
                stub = voc_pb2_grpc.CriticStub(ch)
                cres = await stub.Review(
                    voc_pb2.ReviewReq(
                        doc=result.policy,
                        role="policy"
                    ),
                    timeout=180.0
                )
            
            # ============ 필요시 정책 개선 ============
            # Critic이 개선이 필요하다고 판단한 경우 refine 수행
            final_policy = result.policy
            if cres.need_refine and cres.edits:
                refine_result = await self.imp.refine(
                    result.policy,
                    json.dumps({"edits": list(cres.edits)}, ensure_ascii=False)
                )
                final_policy = refine_result.policy
            
            # ============ Critic의 응답에서 최종 정책 추출 ============
            # Critic이 role="policy"일 때 ReviewRes.policy에 최종 정책을 포함시킴
            # Critic의 응답에 policy가 있으면 우선 사용 (refine된 최종 결과)
            if cres.policy and len(cres.policy.strip()) > 0:
                final_policy = cres.policy.strip()
            
            # ============ 최종 정책 검증 ============
            # 최종 정책이 비어있으면 생성된 정책 사용
            if not final_policy or len(final_policy.strip()) < 20:
                final_policy = result.policy
                if not final_policy or len(final_policy.strip()) < 20:
                    final_policy = "요약 내용을 기반으로 정책 개선안을 생성하려고 시도했으나, 충분한 내용을 생성하지 못했습니다. 요약 내용을 확인하고 다시 시도해 주세요."
            
            # ============ 응답 메시지 생성 및 반환 ============
            # 생성된 정책 개선안을 gRPC 응답 메시지로 감싸서 반환합니다
            return voc_pb2.PolicyRes(policy=final_policy.strip())
        except Exception as e:
            # ============ 에러 처리 ============
            # 예외 발생 시 gRPC 에러로 변환하여 클라이언트에 전달합니다
            await context.abort(grpc.StatusCode.INTERNAL, f"Improver.Improve error: {e}")

    # ============ Refine RPC 구현 ============
    async def Refine(self, request, context):
        """
        Refine RPC를 구현합니다.
        
        클라이언트로부터 원본 정책 개선안과 수정 지침을 받아
        개선된 정책 개선안을 생성하여 반환합니다.
        
        Args:
            request: RefinePolicyReq 메시지 (policy, edits_json 포함)
            context: gRPC 서비스 컨텍스트 (에러 처리 등에 사용)
            
        Returns:
            PolicyRes: 개선된 정책 개선안을 포함한 응답 메시지
        """
        try:
            # ============ 정책 개선안 개선 ============
            # 에이전트의 refine 메서드를 호출하여 정책 개선안을 개선합니다
            result: PolicyResult = await self.imp.refine(
                request.policy,              # 개선할 원본 정책 개선안 텍스트
                request.edits_json or "",    # 수정 지침 (JSON 문자열)
            )
            # ============ 응답 메시지 생성 및 반환 ============
            # 개선된 정책 개선안을 gRPC 응답 메시지로 감싸서 반환합니다
            return voc_pb2.PolicyRes(policy=result.policy)
        except Exception as e:
            # ============ 에러 처리 ============
            # 예외 발생 시 gRPC 에러로 변환하여 클라이언트에 전달합니다
            await context.abort(grpc.StatusCode.INTERNAL, f"Improver.Refine error: {e}")

    # ============ RunPolicyPipeline RPC 구현 ============
    async def RunPolicyPipeline(self, request, context):
        """
        RunPolicyPipeline RPC를 구현합니다.
        
        정책 개선안 생성 전체 파이프라인을 실행합니다.
        Critic을 직접 호출하여 정책을 검토하고 개선합니다.
        
        Args:
            request: RunPolicyPipelineReq 메시지 (summary 포함)
            context: gRPC 서비스 컨텍스트 (에러 처리 등에 사용)
            
        Returns:
            RunPolicyPipelineRes: 정책 개선안 결과 및 추적 정보를 포함한 응답 메시지
        """
        try:
            # ============ 파이프라인 실행 ============
            # 에이전트의 run_policy_pipeline 메서드를 호출하여 전체 파이프라인을 실행합니다
            result = await self.imp.run_policy_pipeline(
                summary=request.summary,
                timeout=180.0,
            )
            # ============ 응답 메시지 생성 및 반환 ============
            # 파이프라인 실행 결과를 gRPC 응답 메시지로 감싸서 반환합니다
            return voc_pb2.RunPolicyPipelineRes(
                ok=result.get("ok", False),
                policy=result.get("policy", ""),
                trace=result.get("trace", ""),
            )

        except Exception as e:
            # ============ 에러 처리 ============
            # 예외 발생 시 gRPC 에러로 변환하여 클라이언트에 전달합니다
            await context.abort(
                grpc.StatusCode.INTERNAL,  # 내부 서버 오류 상태 코드
                f"Improver.RunPolicyPipeline error: {e}"  # 에러 메시지
            )


# ============ gRPC 서버 실행 함수 ============
# 이 모듈을 직접 실행할 때 gRPC 서버를 시작하는 함수
# --------------------------------
# gRPC Server Runner
# --------------------------------

async def serve() -> None:
    """
    Improver gRPC 서버를 시작합니다.
    
    환경변수 IMPROVER_BIND에서 엔드포인트를 읽어옵니다.
    기본값은 "0.0.0.0:6006"입니다 (모든 네트워크 인터페이스의 6006 포트).
    """
    # ============ 엔드포인트 설정 ============
    # 환경변수에서 엔드포인트를 읽어오고, 없으면 기본값을 사용합니다
    bind = os.environ.get("IMPROVER_BIND", "0.0.0.0:6006")

    # ============ gRPC 서버 생성 ============
    # 비동기 gRPC 서버 인스턴스를 생성합니다
    server = grpc.aio.server()
    # ============ 서비스 등록 ============
    # ImproverServicer를 서버에 등록하여 RPC 요청을 처리할 수 있도록 합니다
    voc_pb2_grpc.add_ImproverServicer_to_server(ImproverServicer(), server)
    # ============ 포트 바인딩 ============
    # 서버를 지정된 엔드포인트에 바인딩합니다 (TLS 없이)
    server.add_insecure_port(bind)

    # ============ 서버 시작 로그 ============
    # 서버가 시작되었음을 콘솔에 출력합니다
    print(f"[Improver] gRPC server started on {bind}")
    # ============ 서버 시작 및 대기 ============
    # 서버를 시작하고 종료 신호를 받을 때까지 대기합니다
    await server.start()
    # 서버가 종료될 때까지 무한 대기합니다 (Ctrl+C로 종료 가능)
    await server.wait_for_termination()


# ============ 메인 실행 블록 ============
# 스크립트가 직접 실행될 때만 서버를 시작합니다
if __name__ == "__main__":
    # asyncio.run()을 사용하여 비동기 서버를 실행합니다
    asyncio.run(serve())
