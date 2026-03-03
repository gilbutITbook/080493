# run.py 
"""
MCP (Model Context Protocol) 서버 - 제안서 생성 도구 제공

이 모듈은 MCP 서버로 동작하여 외부에서 제안서 생성 도구를 호출할 수 있도록 합니다.
gRPC 오케스트레이터를 사용하여 실제 제안서 생성 작업을 수행합니다.

주요 기능:
- generate_proposal: 질문과 고객 프로필을 바탕으로 제안서 생성
- gRPC 기반 오케스트레이터와 연동
- MCP 프로토콜을 통한 외부 도구 호출 지원
"""
import os, sys, traceback
from mcp.server.fastmcp import FastMCP
from orchestrator import OrchestratorGrpc  # gRPC 오케스트레이터 사용

# MCP 서버 초기화
# FastMCP를 사용하여 MCP 서버 생성
mcp = FastMCP(name="generate-proposal")


def _elog(msg: str):
    """에러 로그 출력 함수"""
    try:
        # 표준 에러 출력에 메시지 작성 (개행 문자 제거 후 추가)
        sys.stderr.write(str(msg).rstrip() + "\n")
    except Exception:
        # 출력 실패 시 무시 (에러 로그 함수 자체가 실패하지 않도록)
        pass


@mcp.tool(
    name="generate_proposal",
    description="질문(question)과 고객 프로필(profiles_path)을 참조하여 gRPC 기반으로 제안서를 생성하고 .md로 저장"
)
async def generate_proposal(
    question: str,
    profiles_path: str,
    company: str = "Azure AI Foundry",
    market: str = "FSI",
    save: bool = True,
    out_dir: str = "outputs",
) -> str:
    """
    MCP 도구 - gRPC 오케스트레이터를 호출하여 제안서를 생성합니다.
    """
    try:
        # A2A 구조에 맞춘 오케스트레이터 초기화 
        # gRPC 기반 오케스트레이터 인스턴스 생성
        orch = OrchestratorGrpc()

        # 전체 파이프라인 실행
        # 경쟁사 분석, 고객 분석, 기능 제안, 수익모델 도출, 마크다운 저장을 순차적으로 수행
        # out_filename은 내부적으로 None으로 처리 (자동 생성)
        out = await orch.generate_proposal(
            question=question,
            profiles_path=profiles_path,
            company=company,
            market=market,
            out_dir=out_dir,
            out_filename=None,  # UI에 표시하지 않고 내부적으로 None 처리
            save=save,
        )

        # 실행 결과 메시지 구성
        # 성공/실패 여부에 따라 메시지 라인 구성
        lines = ["generate_proposal 완료" if out.get("ok") else "generate_proposal 실패"]
        # 저장된 파일 경로가 있으면 추가
        if out.get("saved_path"):
            lines.append(f"- saved: {out['saved_path']}")
        # 실패한 경우 오류 메시지 추가
        if not out.get("ok"):
            lines.append(f"- error: {out.get('error')}")
        # 모든 메시지 라인을 개행문자로 결합하여 반환
        return "\n".join(lines)

    except Exception:
        # 예외 발생 시 전체 스택 트레이스 출력
        _elog(traceback.format_exc())
        return "generate_proposal 실패"


# 직접 실행 시 MCP 서버를 시작하는 진입점
if __name__ == "__main__":
    """MCP 서버 실행 - stdio 기반"""
    # stdio 전송 방식을 사용하여 MCP 서버 실행
    # 표준 입출력을 통해 MCP 프로토콜 통신
    mcp.run(transport="stdio")
