# main.py
# MCP 서버: RFP Compliance Matrix 생성
#
# - 에이전트 간 직접 통신 기반 (A2A)
# - ComplianceMatrixAgent를 gRPC로 호출 (6052 포트)
# - ComplianceMatrixAgent가 필요 시 OutlineAgent를 gRPC로 직접 호출 (6051 포트)
# - Orchestrator 없이 에이전트 간 직접 통신으로 동작
# - MCP 툴로 동작

import os, asyncio
from typing import Dict, Any

from mcp.server.fastmcp import FastMCP
from grpc_client import GrpcClient

# FastMCP 서버 인스턴스 생성
mcp = FastMCP(name="RFP-A2A-MCP")


def _resolve_pdf_path(pdf_path: str | None) -> str:
    """
    PDF 파일 경로 해석
    - 여러 후보 경로를 확인하여 실제 존재하는 파일 찾기
    """
    # 스크립트 디렉토리와 워크스페이스 루트 경로 설정
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    WORKSPACE_ROOT = os.environ.get("RFP_WORKSPACE_ROOT", SCRIPT_DIR)
    
    if not pdf_path:
        # 기본값: 여러 후보 경로에서 RFP.pdf 찾기
        candidates = [
            os.path.join(os.getcwd(), "RFP.pdf"),  # 현재 작업 디렉토리
            os.path.join(SCRIPT_DIR, "RFP.pdf"),  # 스크립트 디렉토리 (프로젝트 루트)
            os.path.join(WORKSPACE_ROOT, "RFP.pdf"),  # 워크스페이스 루트
        ]
        
        # 중복 제거
        candidates = list(dict.fromkeys(candidates))
        
        # 후보 경로 중 실제 존재하는 파일 찾기
        for c in candidates:
            if os.path.exists(c):
                return os.path.abspath(c)
        
        raise FileNotFoundError(
            f"pdf_path is required (or RFP.pdf not found in: {candidates})"
        )

    # 절대 경로인 경우 그대로 사용
    if os.path.isabs(pdf_path):
        if os.path.exists(pdf_path):
            return os.path.abspath(pdf_path)
        else:
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # 상대 경로인 경우 여러 후보 경로 생성
    candidates = [
        os.path.abspath(pdf_path),  # 현재 작업 디렉토리 기준
        os.path.join(SCRIPT_DIR, pdf_path),  # 스크립트 디렉토리 기준
        os.path.join(WORKSPACE_ROOT, pdf_path),  # 워크스페이스 루트 기준
    ]
    
    # 중복 제거
    candidates = list(dict.fromkeys(candidates))

    # 후보 경로 중 실제 존재하는 파일 찾기
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)

    raise FileNotFoundError(f"PDF not found in candidates: {candidates}")


async def _ensure_server_reachable(client: GrpcClient, addr: str) -> None:
    """
    gRPC 서버 연결 가능 여부 확인
    - health.ping 토픽으로 헬스체크 수행
    - 10초 타임아웃으로 서버 준비 시간 허용
    """
    try:
        # 헬스체크 요청 (10초 타임아웃)
        pong = await asyncio.wait_for(client.request("health.ping", {}), timeout=10.0)
        # 응답이 실패인 경우
        if not pong.get("ok"):
            raise RuntimeError(pong.get("error", "health.ping failed"))
    except Exception as e:
        # 서버에 연결할 수 없는 경우 예외 발생
        raise RuntimeError(f"gRPC Compliance server not reachable at {addr}: {e}")


async def _run_compliance(pdf_path: str | None = None, out_path: str | None = None, hints: str | None = None) -> Dict[str, Any]:
    """
    ComplianceMatrixAgent를 gRPC로 호출하는 공통 함수
    - MCP 툴에서 사용
    """
    # OpenAI API 키 확인
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    # Compliance 에이전트 gRPC 주소
    compliance_addr = os.getenv("RFP_COMPLIANCE_ADDR", "127.0.0.1:6052")

    # PDF 경로 해석
    resolved_pdf = _resolve_pdf_path(pdf_path)

    # ComplianceMatrixAgent와 통신할 gRPC 클라이언트 생성
    # 타임아웃을 300초(5분)로 늘려 LLM 처리 시간 확보
    client = GrpcClient(compliance_addr, timeout_sec=300.0)
    
    # 서버 연결 가능 여부 확인
    await _ensure_server_reachable(client, compliance_addr)

    # 페이로드 구성
    payload: Dict[str, Any] = {
        "pdf_path": resolved_pdf,
    }
    if out_path:
        payload["out_path"] = out_path
    if hints:
        payload["hints"] = hints

    # ComplianceMatrixAgent를 gRPC로 호출
    result = await client.request("compliance.build", payload)
    return result


@mcp.tool()
async def rfp_orchestrator(pdf_path: str | None = None, out_path: str | None = None, hints: str | None = None) -> dict:
    """
    RFP PDF에서 ComplianceMatrix를 생성하는 multi-agent 파이프라인을 실행합니다.
    
    Args:
        pdf_path: RFP PDF 파일 경로 (기본값: RFP.pdf)
        out_path: 출력 XLSX 파일 경로 (기본값: <PDF이름>.rfp_compliance.xlsx)
        hints: 목차 추출 힌트 (선택사항)
    
    Returns:
        생성된 Excel 파일 경로와 메타 정보
    """
    try:
        result = await _run_compliance(pdf_path, out_path, hints)
        
        # 성공 응답
        if result.get("ok"):
            return {
                "ok": True,
                "file": result.get("file"),
                "rows": result.get("rows"),
                "coverage_gaps": result.get("coverage_gaps", []),
                "outline_used": result.get("outline_used", []),
            }
        else:
            return {
                "ok": False,
                "error": result.get("error", "unknown error"),
            }
    except Exception as e:
        import traceback
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }


if __name__ == "__main__":
    """
    MCP 서버 모드: stdio를 통해 JSON-RPC 통신
    에이전트 간 직접 통신 기반 (A2A):
    - 두 에이전트 모두 gRPC 서버로 별도 프로세스에서 구동되어야 함:
      - OutlineAgent: 6051 포트
      - ComplianceMatrixAgent: 6052 포트
    """
    mcp.run(transport="stdio")
