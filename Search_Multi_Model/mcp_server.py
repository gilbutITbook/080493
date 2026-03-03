# mcp_server.py
"""
MCP (Model Context Protocol) 서버 모듈
FastMCP를 사용하여 A2A 파이프라인을 MCP 도구로 노출합니다.
"""
import os
from mcp.server.fastmcp import FastMCP
from orchestrator import Orchestrator

# FastMCP 서버 인스턴스 생성
mcp = FastMCP()

# 오케스트레이터 인스턴스 생성 (전역으로 관리)
orc = Orchestrator()

@mcp.tool(name="a2a.run")
def run_pipeline(task: str, debug: bool = False) -> dict:
    """
    A2A 파이프라인을 실행하는 MCP 도구
    
    Args:
        task: 실행할 작업 설명 문자열
        debug: 디버그 모드 활성화 여부 (추적 정보 포함)
        
    Returns:
        파이프라인 실행 결과 딕셔너리
    """
    return orc.run(task, debug=debug)

@mcp.tool(name="health")
def health() -> dict:
    """
    시스템 상태를 확인하는 MCP 도구
    각 에이전트 서버의 주소를 반환합니다.
    
    Returns:
        상태 정보와 에이전트 주소 딕셔너리
    """
    return {"status": "ok", "agents": {
        "draft": os.getenv("A2A_DRAFT_ADDR", "localhost:6001"),
        "critic": os.getenv("A2A_CRITIC_ADDR", "localhost:6002"),
        "scoring": os.getenv("A2A_SCORING_ADDR", "localhost:6003"),
        "synth": os.getenv("A2A_SYNTH_ADDR", "localhost:6004"),
    }}

if __name__ == "__main__":
    # MCP 서버 실행
    mcp.run(transport="stdio")
