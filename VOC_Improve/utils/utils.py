# =============================================
# File: utils.py
# =============================================
# VOC 분석 시스템의 유틸리티 함수들
# 
# 주요 기능:
# - Windows 환경에서 UTF-8 인코딩 강제 설정
# - 필터 문자열 파싱 및 정규화
# - 다양한 구분자를 지원하는 키워드 추출

# ============ 표준 라이브러리 및 타입 힌트 임포트 ============
# 운영체제 관련 기능 (환경변수 설정 등)
import os
# 시스템 관련 기능 (표준 입출력 스트림 제어 등)
import sys
# 정규표현식 지원 (문자열 패턴 매칭)
import re
# 타입 힌트를 위한 타입 정의들
from typing import Optional, List

# ============ 인코딩 설정 ============
# Windows 환경에서 한글 등 멀티바이트 문자가 올바르게 출력되도록 설정합니다
# 이 설정은 모듈이 임포트될 때 자동으로 실행됩니다

# ---- Windows 콘솔에서 UTF-8 인코딩 강제 설정 ----
# Windows 환경에서 한글 출력 문제를 방지하기 위한 설정
# PYTHONUTF8 환경변수를 설정하여 Python이 UTF-8을 기본 인코딩으로 사용하도록 합니다
os.environ.setdefault("PYTHONUTF8", "1")
# PYTHONIOENCODING 환경변수를 설정하여 입출력 인코딩을 UTF-8로 지정합니다
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    # 표준 출력/에러 스트림을 UTF-8로 재설정
    # reconfigure() 메서드는 Python 3.7+에서 사용 가능합니다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    # 재설정 실패 시 무시 (호환성 문제 방지)
    # Python 버전이 낮거나 스트림이 재설정 불가능한 경우를 대비합니다
    pass


# ============ 유틸리티 함수 ============

def parse_filters(filters: Optional[str]) -> Optional[List[str]]:
    """
    필터 문자열을 키워드 리스트로 변환하는 함수
    
    다양한 구분자를 지원하여 사용자가 다양한 형태로 입력한 
    필터 문자열을 파싱합니다.
    
    지원하는 구분자:
    - 콤마 (,)
    - 슬래시 (/)
    - 세미콜론 (;)
    - 2칸 이상 공백
    - 따옴표로 둘러싸인 문자열 ("...")
    
    Args:
        filters: 파싱할 필터 문자열 (예: '앱 오류, 대기/불친절')
        
    Returns:
        Optional[List[str]]: 파싱된 키워드 리스트 (None if filters is None or empty)
        
    Examples:
        >>> parse_filters('앱 오류, 대기/불친절')
        ['앱 오류', '대기', '불친절']
        >>> parse_filters('"앱 오류" 대기  불친절')
        ['앱 오류', '대기', '불친절']
    """
    # ============ 입력 검증 ============
    # 필터 문자열이 None이거나 빈 문자열이면 None을 반환합니다
    if not filters:
        return None
    
    # ============ 1단계: 따옴표로 둘러싸인 키워드 추출 ============
    # 큰따옴표로 둘러싸인 문자열을 먼저 추출합니다
    # 예: "앱 오류" -> "앱 오류" 추출
    # 정규표현식 r'"([^"]+)"'는 큰따옴표 안의 내용을 캡처합니다
    quoted = re.findall(r'"([^"]+)"', filters)
    
    # ============ 2단계: 나머지 문자열에서 구분자로 분리 ============
    # 따옴표로 둘러싸인 부분을 제거한 나머지 문자열에서
    # 콤마, 슬래시, 세미콜론, 또는 2칸 이상 공백으로 구분된 키워드를 추출합니다
    rest = re.sub(r'"([^"]+)"', "", filters)  # 따옴표 부분 제거
    # 정규표현식 r"[,;/]+|\s{2,}"는 콤마/슬래시/세미콜론 또는 2칸 이상 공백을 매칭합니다
    parts = re.split(r"[,;/]+|\s{2,}", rest)
    
    # ============ 3단계: 모든 토큰을 결합하고 빈 문자열 제거 ============
    # 따옴표로 둘러싸인 키워드와 구분자로 분리된 키워드를 합칩니다
    # 각 토큰의 앞뒤 공백을 제거하고, 빈 문자열은 제외합니다
    tokens = [t.strip() for t in (quoted + parts) if t and t.strip()]
    
    # ============ 4단계: 결과 반환 ============
    # 유효한 토큰이 있으면 리스트를 반환하고, 없으면 None을 반환합니다
    # or 연산자를 사용하여 빈 리스트를 None으로 변환합니다
    return tokens or None

