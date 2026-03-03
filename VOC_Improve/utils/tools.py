# =============================================
# File: utils/tools.py  
# =============================================
# MCP(Model Context Protocol) 기반 VOC 분석 도구 모음
#
# 주요 기능:
# - Claude Desktop/Cursor와의 MCP 통합
# - 자연어 질의를 gRPC 파이프라인으로 변환
# - VOC 데이터 분석 및 정책 개선안 생성
# - gRPC 런타임 싱글톤 관리
#
# 이 모듈은 외부 MCP 클라이언트가 VOC 분석 시스템을 사용할 수 있도록
# 하는 인터페이스를 제공하며, 자연어 질의를 구조화된 파라미터로 변환하여
# gRPC 기반 에이전트 파이프라인에 전달합니다.

# ============ 표준 라이브러리 및 외부 패키지 임포트 ============
# 운영체제 관련 기능 (환경변수 읽기, 경로 처리 등)
import os
# 시스템 관련 기능 (sys.path 조작 등)
import sys
# 정규표현식 지원 (키워드 추출 등)
import re
# 동적 모듈 임포트 지원 (지연 로딩)
import importlib
# 타입 힌트를 위한 타입 정의들
from typing import Dict
# MCP 서버 프레임워크 (Claude Desktop/Cursor와 통신)
from mcp.server.fastmcp import FastMCP

# ============ 프로젝트 루트 경로 설정 ============
# 프로젝트 루트 경로를 sys.path에 추가하여 모듈 임포트 보장
# 이렇게 하면 다른 디렉토리에서도 이 모듈을 임포트할 수 있습니다
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.append(ROOT)

# ============ 프로젝트 내부 모듈 임포트 ============
# 필터 파싱 유틸리티 함수
from utils.utils import parse_filters
# 기본 CSV 경로 설정
from utils.settings import DEFAULT_CSV

# ============ MCP 서버 인스턴스 생성 ============
# MCP 서버 인스턴스 생성 (Claude Desktop/Cursor와 통신)
# FastMCP는 MCP 프로토콜을 구현하는 서버 프레임워크입니다
mcp = FastMCP(name="voc_mcp")

# ============ gRPC 런타임 관리 ============

# 싱글톤 패턴으로 gRPC 런타임 관리 (메모리 효율성과 상태 일관성 보장)
_runtime = None

def get_runtime():
    """
    gRPC 런타임 인스턴스를 싱글톤 패턴으로 반환
    
    grpc_server 모듈의 A2AGRPCRuntime 또는 VOCGRPCRuntime을 사용합니다.
    지연 임포트를 통해 모듈 의존성을 최소화합니다.
    
    Returns:
        VOCGRPCRuntime: gRPC 런타임 인스턴스 (싱글톤)
    """
    global _runtime
    if _runtime is None:
        # 지연 임포트로 grpc_server 모듈 로드
        mod = importlib.import_module("grpc_server")
        # 호환성을 위해 A2AGRPCRuntime 또는 VOCGRPCRuntime 중 사용 가능한 것 선택
        RuntimeCls = getattr(mod, "A2AGRPCRuntime", getattr(mod, "VOCGRPCRuntime"))
        _runtime = RuntimeCls()
    return _runtime

# ============ 키워드 추출 유틸리티 ============

# 자연어 텍스트에서 키워드를 추출하기 위한 정규표현식 패턴
# 한글, 영문, 숫자로 구성된 토큰을 찾음
_TOKEN = re.compile(r"[가-힣A-Za-z0-9]+")

# 키워드 추출 시 제외할 불용어 집합 (의미 있는 키워드만 추출하기 위함)
# 일반적인 조사, 어미, 불필요한 단어들을 제외
STOPWORDS = {"정책","개선안","제시","방안","요청","voc","관련","중심","분석","데이터","해줘","해주세요","좀"}

# 동의어 매핑 딕셔너리 (유사한 의미의 키워드를 표준 형태로 정규화)
# 같은 의미의 다양한 표현을 하나의 표준 키워드로 통일
SYNONYMS = {"불친절":["불친절","태도"], "대기":["대기","지연","대기시간"], "상담":["상담","콜센터","상담원"]}

def _norm(t: str) -> str:
    """
    키워드를 표준 형태로 정규화하는 함수
    
    동의어 매핑을 사용하여 유사한 의미의 키워드들을 
    하나의 표준 형태로 통일합니다.
    
    Args:
        t: 정규화할 키워드 문자열
        
    Returns:
        str: 정규화된 키워드 (동의어가 있으면 표준 형태로 변환)
    """
    t = t.lower()  # 소문자로 변환
    for base, vs in SYNONYMS.items():
        if t == base or t in vs:
            return base  # 동의어가 있으면 표준 형태 반환
    return t  # 동의어가 없으면 원본 반환

def extract_keywords(text: str, min_len: int = 2, max_cnt: int = 6):
    """
    자연어 텍스트에서 의미 있는 키워드를 추출하는 함수
    
    정규표현식을 사용하여 토큰을 추출하고, 불용어를 제거한 후
    동의어 정규화를 통해 의미 있는 키워드만 선별합니다.
    
    Args:
        text: 키워드를 추출할 텍스트
        min_len: 최소 키워드 길이 (기본값: 2)
        max_cnt: 최대 키워드 개수 (기본값: 6)
        
    Returns:
        List[str]: 추출된 키워드 리스트
    """
    # 1단계: 정규표현식으로 토큰 추출 (최소 길이 이상)
    toks = [t for t in _TOKEN.findall(text or "") if len(t) >= min_len]
    
    # 2단계: 소문자 변환 및 불용어 제거
    toks = [t.lower() for t in toks if t.lower() not in STOPWORDS]
    
    # 3단계: 중복 제거하면서 정규화된 키워드 추출
    out = []
    for t in map(_norm, toks):
        if len(t) >= min_len and t not in out:
            out.append(t)
    
    return out[:max_cnt]  # 최대 개수만큼만 반환

# ============ MCP 도구 정의 ============

@mcp.tool(name="analyze_voc_nl_v2",
          description="자연어 질의를 gRPC 파이프라인으로 전달해 VOC 분석(요약+정책) 실행")
async def analyze_voc_nl_v2(question: str, csv_path: str = DEFAULT_CSV) -> Dict:
    """
    자연어 질의를 받아서 전체 VOC 분석 파이프라인을 실행하는 MCP 도구
    
    이 도구는 사용자의 자연어 질의를 받아 gRPC 파이프라인을 통해
    VOC 데이터 분석부터 정책 개선안 생성까지 전체 과정을 수행합니다.
    실패 시 키워드 기반 폴백 실행을 제공합니다.
    
    Args:
        question: 사용자의 자연어 질의 (예: "상담 대기 시간과 불친절 관련 불만사항 분석")
        csv_path: VOC 데이터 CSV 파일 경로
        
    Returns:
        Dict: 분석 결과 (요약, 정책 개선안, 추적 정보 포함)
    """
    try:
        # ============ 1단계: gRPC 런타임 인스턴스 가져오기 ============
        # 싱글톤 패턴으로 관리되는 gRPC 런타임 인스턴스를 가져옵니다
        rt = get_runtime()
        
        # ============ 2단계: 자연어 질의로 gRPC 파이프라인 실행 ============
        # 자연어 질의를 받아 전체 VOC 분석 파이프라인을 실행합니다
        # Interpreter가 질의를 파싱하고, Retriever, Summarizer, Evaluator, Critic, Improver가 순차적으로 실행됩니다
        out = await rt.run_with_question(question=question, csv_path=csv_path, timeout=180.0)
        
        # ============ 3단계: 과거 키와 호환성 유지 ============
        # 새로운 키("summary", "policy")와 과거 키("요약", "정책_개선안")를 모두 제공하여
        # 기존 코드와의 호환성을 유지합니다
        if "요약" not in out and "summary" in out: 
            out["요약"] = out["summary"]
        if "정책_개선안" not in out and "policy" in out: 
            out["정책_개선안"] = out["policy"]
        return out
        
    except Exception as e:
        # ============ 폴백: 키워드 기반 실행 ============
        # 자연어 질의 파싱이 실패한 경우, 키워드를 추출하여 직접 파라미터로 실행합니다
        # 이렇게 하면 Interpreter가 실패해도 분석을 수행할 수 있습니다
        try:
            # ============ 1단계: 자연어 질의에서 키워드 추출 ============
            # 자연어 질의에서 의미 있는 키워드를 추출합니다
            # 추출 실패 시 기본 키워드(상담, 대기, 지연, 불친절)를 사용합니다
            kw = extract_keywords(question) or ["상담","대기","지연","불친절"]
            
            # ============ 2단계: gRPC 런타임으로 키워드 기반 실행 ============
            # 추출한 키워드를 필터로 사용하여 VOC 분석을 실행합니다
            # Interpreter를 거치지 않고 직접 파라미터를 지정합니다
            rt = get_runtime()
            out = await rt.run_with_params(filters=kw, task="both", max_items=50, csv_path=csv_path, timeout=180.0)
            
            # ============ 3단계: 과거 키와 호환성 유지 ============
            # 새로운 키와 과거 키를 모두 제공합니다
            if "요약" not in out and "summary" in out: 
                out["요약"] = out["summary"]
            if "정책_개선안" not in out and "policy" in out: 
                out["정책_개선안"] = out["policy"]
            
            # ============ 4단계: 폴백 실행임을 표시 ============
            # 폴백 모드로 실행되었음을 결과에 표시합니다
            out.setdefault("ok", True)
            out.setdefault("note", "fallback: keyword-based run")
            return out
            
        except Exception as e2:
            # ============ 모든 시도 실패 처리 ============
            # 자연어 질의 파싱과 키워드 기반 실행 모두 실패한 경우
            # 오류 메시지를 포함한 결과를 반환합니다
            return {"ok": False, "error": f"analyze_voc_nl_v2_failed: {e}; fallback {e2}"}

@mcp.tool(name="analyze_voc", description="filters는 문자열로 입력. 예: '앱 오류, 대기/불친절'")
async def analyze_voc(filters: str | None = None, task: str = "both", max_items: int = 30, csv_path: str = DEFAULT_CSV) -> Dict:
    """
    직접 파라미터를 지정하여 VOC 분석을 수행하는 MCP 도구
    
    자연어 질의 대신 직접 필터 키워드와 작업 유형을 지정하여 VOC 분석을 수행합니다.
    더 정확한 제어가 필요한 경우에 사용됩니다.
    
    Args:
        filters: 필터링할 키워드 문자열 (예: "앱 오류, 대기/불친절")
        task: 수행할 작업 유형 ("summary", "policy", "both")
        max_items: 분석할 최대 VOC 개수 (5~200)
        csv_path: VOC 데이터 CSV 파일 경로
        
    Returns:
        Dict: 분석 결과
    """
    try:
        # ============ 1단계: gRPC 런타임 인스턴스 가져오기 ============
        # 싱글톤 패턴으로 관리되는 gRPC 런타임 인스턴스를 가져옵니다
        rt = get_runtime()
        
        # ============ 2단계: 필터 문자열을 파싱하여 리스트로 변환 ============
        # 사용자가 제공한 필터 문자열(예: "앱 오류, 대기/불친절")을
        # 키워드 리스트로 파싱합니다
        fl = parse_filters(filters)
        
        # ============ 3단계: 최대 아이템 수 범위 제한 ============
        # 최대 아이템 수를 5~200 범위로 제한하여 안정성을 확보합니다
        # 너무 적거나 많으면 성능 문제가 발생할 수 있습니다
        max_items = max(5, min(200, int(max_items or 30)))
        
        # ============ 4단계: gRPC 파이프라인 실행 ============
        # 파싱된 필터와 파라미터를 사용하여 VOC 분석 파이프라인을 실행합니다
        # Interpreter를 거치지 않고 직접 파라미터를 지정합니다
        out = await rt.run_with_params(filters=fl, task=task, max_items=max_items, csv_path=csv_path, timeout=180.0)
        
        # ============ 5단계: 과거 키와 호환성 유지 ============
        # 새로운 키와 과거 키를 모두 제공하여 기존 코드와의 호환성을 유지합니다
        if "요약" not in out and "summary" in out: 
            out["요약"] = out["summary"]
        if "정책_개선안" not in out and "policy" in out: 
            out["정책_개선안"] = out["policy"]
        return out
        
    except Exception as e:
        # ============ 오류 처리 ============
        # 오류 발생 시 안전한 오류 메시지를 포함한 결과를 반환합니다
        return {"ok": False, "error": f"analyze_voc_failed: {e}"}

@mcp.tool(name="health_check", description="CSV 경로/접근 점검")
async def health_check(csv_path: str = DEFAULT_CSV) -> Dict:
    """
    CSV 파일의 존재 여부와 접근 가능성을 점검하는 MCP 도구
    
    시스템이 VOC 데이터 파일에 정상적으로 접근할 수 있는지 확인합니다.
    파일 크기 정보도 함께 제공하여 데이터 양을 파악할 수 있습니다.
    
    Args:
        csv_path: 점검할 CSV 파일 경로
        
    Returns:
        Dict: 점검 결과 (파일 존재 여부, 경로, 크기 정보)
    """
    try:
        # ============ pathlib 임포트 ============
        # 파일 경로 처리를 위해 pathlib을 임포트합니다
        import pathlib
        
        # ============ 1단계: 파일 경로 객체 생성 ============
        # 문자열 경로를 pathlib.Path 객체로 변환합니다
        # 이렇게 하면 크로스 플랫폼 경로 처리가 가능합니다
        p = pathlib.Path(csv_path)
        
        # ============ 2단계: 파일 존재 여부 확인 ============
        # 파일이 실제로 존재하는지 확인합니다
        ok = p.exists()
        
        # ============ 3단계: 파일 크기 정보 추출 ============
        # 파일이 존재하는 경우에만 파일 크기를 가져옵니다
        # 파일이 없으면 None을 반환합니다
        size = p.stat().st_size if ok else None
        
        # ============ 4단계: 점검 결과 반환 ============
        # 파일 존재 여부, 절대 경로, 파일 크기를 포함한 결과를 반환합니다
        return {"ok": ok, "csv_path": str(p.resolve()), "size": size}
        
    except Exception as e:
        # ============ 오류 처리 ============
        # 오류 발생 시 오류 정보와 함께 결과를 반환합니다
        # 원본 경로도 포함하여 디버깅에 도움이 되도록 합니다
        return {"ok": False, "error": str(e), "csv_path": csv_path}

@mcp.tool(name="summarize_voc", description="VOC CSV 요약만 생성")
async def summarize_voc(max_items: int = 30, csv_path: str = DEFAULT_CSV) -> str:
    """
    VOC 데이터 요약만 생성하는 MCP 도구
    
    정책 개선안 생성 없이 VOC 데이터의 요약만 필요한 경우에 사용됩니다.
    빠른 데이터 인사이트가 필요한 상황에 적합합니다.
    
    Args:
        max_items: 분석할 최대 VOC 개수
        csv_path: VOC 데이터 CSV 파일 경로
        
    Returns:
        str: 생성된 요약 텍스트
    """
    try:
        # ============ 1단계: gRPC 런타임 인스턴스 가져오기 ============
        # 싱글톤 패턴으로 관리되는 gRPC 런타임 인스턴스를 가져옵니다
        rt = get_runtime()
        
        # ============ 2단계: 요약만 생성하도록 task를 "summary"로 설정 ============
        # 필터 없이 전체 VOC 데이터를 요약합니다
        # task를 "summary"로 설정하여 정책 개선안 생성은 건너뜁니다
        out = await rt.run_with_params(filters=None, task="summary", max_items=max_items, csv_path=csv_path, timeout=180.0)
        
        # ============ 3단계: 요약 텍스트 추출하여 반환 ============
        # 결과에서 요약 텍스트를 추출합니다
        # 새로운 키("summary")와 과거 키("요약") 모두 확인합니다
        return out.get("summary") or out.get("요약", "")
        
    except Exception as e:
        # ============ 오류 처리 ============
        # 오류 발생 시 오류 메시지를 포함한 문자열을 반환합니다
        return f"[error] summarize_voc_failed: {e}"

@mcp.tool(name="policy_from_summary", description="요약 텍스트 → 정책 개선안 생성")
async def policy_from_summary(summary: str) -> str:
    """
    기존 요약 텍스트를 바탕으로 정책 개선안을 생성하는 MCP 도구
    
    이미 생성된 요약이 있는 경우, 이를 바탕으로 정책 개선안만 생성할 때 사용됩니다.
    요약과 정책 생성을 분리하여 처리하고 싶은 경우에 유용합니다.
    
    Args:
        summary: 기존에 생성된 요약 텍스트
        
    Returns:
        str: 생성된 정책 개선안 텍스트
    """
    try:
        # ============ 1단계: PolicyImproverAgent 직접 import 및 인스턴스 생성 ============
        # gRPC 파이프라인을 거치지 않고 직접 PolicyImproverAgent를 사용합니다
        # 이렇게 하면 요약만 있고 정책 개선안만 필요한 경우 효율적입니다
        from agents.improver import PolicyImproverAgent
        imp = PolicyImproverAgent()
        
        # ============ 2단계: 요약 텍스트를 바탕으로 정책 개선안 생성 ============
        # 요약 텍스트를 기반으로 정책 개선안을 생성합니다
        # gRPC를 거치지 않고 직접 에이전트를 호출합니다
        result = await imp.improve(summary)
        return result.policy
        
    except Exception as e:
        # ============ 오류 처리 ============
        # 오류 발생 시 오류 메시지를 포함한 문자열을 반환합니다
        return f"[error] policy_from_summary_failed: {e}"
