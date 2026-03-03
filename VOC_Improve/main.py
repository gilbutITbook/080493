# =============================================
# File: main.py
# =============================================
# VOC(Voice of Customer) 분석 시스템의 메인 진입점
# MCP(Model Context Protocol) 서버로 동작하여 Claude Desktop/Cursor와 통신
# 
# 주요 역할:
# - MCP 서버 실행 및 도구 노출
# - utils/tools.py에서 정의된 MCP 도구들을 외부 클라이언트에 제공
# 
# 참고: 실제 분석 로직과 오케스트레이션은 utils/tools.py 및 gRPC 기반 모듈에서 수행됩니다.
# main.py는 MCP 인터페이스 계층을 제공하는 역할만 담당합니다.

# ============ 모듈 임포트 ============
# MCP 도구들을 등록하고 서버를 시작하기 위해 utils.tools 모듈에서 mcp 인스턴스를 가져옵니다
# 이 mcp 인스턴스는 FastMCP 서버 객체로, 모든 MCP 도구들이 등록되어 있습니다
from utils.tools import mcp  # ← 루트의 tools.py에서 mcp 가져오기

# ============ 메인 실행 블록 ============
# 스크립트가 직접 실행될 때만 MCP 서버를 시작합니다
# 이렇게 하면 모듈로 임포트될 때는 서버가 시작되지 않습니다
if __name__ == "__main__":
    # MCP 서버를 실행하여 Claude Desktop/Cursor와 통신 시작
    # utils/tools.py에서 정의된 모든 MCP 도구들이 활성화됨
    # 서버는 비동기 이벤트 루프를 통해 실행되며, 클라이언트의 요청을 처리합니다
    mcp.run(transport="stdio")
    # 서버가 종료될 때까지 여기서 대기합니다
    # Ctrl+C로 종료할 수 있습니다