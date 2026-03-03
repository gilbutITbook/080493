# =============================================
# utils.py — 공용 유틸리티 함수들
# =============================================
"""
고객 데이터 처리에 필요한 공통 유틸리티 함수들
날짜 파싱, 구매 이력 분석, 헤더 매핑 등의 기능 제공

이 모듈은 고객 데이터 전처리 과정에서 반복적으로 사용되는 
기본적인 유틸리티 함수들을 제공합니다. 모든 에이전트와 
데이터 로더에서 공통으로 사용할 수 있도록 설계되었습니다.
"""
from __future__ import annotations
import re
from datetime import datetime, date
from typing import Optional, List, Tuple

import os

# ---------- OpenAI API 설정 ----------
# 환경 변수에서 OpenAI API 키를 가져옴
# API 키가 설정되지 않은 경우 None이 되어 LLM 기능이 비활성화됨
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 환경 변수에서 OpenAI 모델명을 가져옴
# 기본값은 "gpt-5.2" (환경 변수가 설정되지 않은 경우)
# 다른 모델을 사용하려면 환경 변수에 OPENAI_MODEL을 설정하면 됨
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")

# 한국어 컬럼 헤더 매핑
# 데이터 파일의 한국어 헤더를 영어 키로 매핑하여 
# 코드에서 일관되게 사용할 수 있도록 합니다.
KOREAN_HEADERS = {
    "id": "고객ID",           # 고객 식별자
    "signup": "회원가입일",    # 가입일
    "history": "물품구매이력", # 구매 이력
    "churn_date": "탈퇴일",   # 탈퇴일
    "churn_reason": "탈퇴사유", # 탈퇴 사유
}

# 날짜 패턴 정규식 (YYYY-MM-DD 형식)
# 구매 이력에서 날짜를 추출하기 위한 정규식 패턴
DATE_PAT = re.compile(r"\d{4}-\d{2}-\d{2}")

def parse_date(s: Optional[str]) -> Optional[date]:
    """
    문자열을 날짜 객체로 변환
    
    이 함수는 안전하게 문자열을 날짜 객체로 변환합니다.
    잘못된 형식이나 None 값에 대해서는 None을 반환합니다.
    
    Args:
        s: 날짜 문자열 (YYYY-MM-DD 형식)
        
    Returns:
        Optional[date]: 변환된 날짜 객체, 실패시 None
    """
    # None이거나 빈 문자열인 경우 None 반환
    if not s: 
        return None
    
    # 앞뒤 공백 제거
    s = s.strip()
    if not s: 
        return None
    
    try:
        # YYYY-MM-DD 형식으로 파싱 (처음 10자리만 사용)
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        # 파싱 실패시 None 반환
        return None

def today() -> date:
    """
    오늘 날짜 반환
    
    시계열 계산이나 날짜 비교에 사용되는 현재 날짜를 반환합니다.
    
    Returns:
        date: 오늘 날짜 객체
    """
    return date.today()

def parse_purchase_history(history: str) -> List[Tuple[date, str]]:
    """
    구매 이력 문자열을 파싱하여 (날짜, 상품명) 튜플 리스트로 변환
    
    이 함수는 구매 이력 문자열에서 날짜와 상품명을 추출하여 
    정렬된 튜플 리스트로 변환합니다. 다양한 구분자를 지원합니다.
    
    Args:
        history: 구매 이력 문자열 (예: "2023-01-01 상품A, 2023-01-02 상품B")
        
    Returns:
        List[Tuple[date, str]]: (구매일, 상품명) 튜플들의 리스트 (날짜순 정렬)
    """
    # 빈 문자열인 경우 빈 리스트 반환
    if not history: 
        return []
    
    items = []
    
    # 쉼표, 줄바꿈, 세미콜론으로 구분하여 각 항목 처리
    # 다양한 구분자를 지원하여 유연한 입력 형식을 처리
    for chunk in re.split(r"[,\n;]+", history):
        chunk = (chunk or "").strip()
        if not chunk: 
            continue
        
        # 날짜 패턴 찾기 (YYYY-MM-DD 형식)
        m = DATE_PAT.search(chunk)
        if not m: 
            continue
        
        # 날짜 파싱
        d = parse_date(m.group(0))
        # 상품명 추출 (날짜 이후 부분)
        name = chunk[m.end():].strip()
        
        # 날짜 파싱이 성공한 경우만 리스트에 추가
        if d: 
            items.append((d, name))
    
    # 날짜순으로 정렬 (오래된 구매부터 최신 구매 순)
    items.sort(key=lambda x: x[0])
    return items

def days_between(a: Optional[date], b: Optional[date]) -> Optional[int]:
    """
    두 날짜 사이의 일수 계산
    
    이 함수는 두 날짜 사이의 일수 차이를 계산합니다.
    고객의 가입 기간, 최근 구매 후 경과 일수 등을 계산할 때 사용됩니다.
    
    Args:
        a: 시작 날짜
        b: 종료 날짜
        
    Returns:
        Optional[int]: 일수 차이 (b - a), None이 있으면 None 반환
    """
    # None 값이 있으면 None 반환
    if not a or not b: 
        return None
    
    # 날짜 차이 계산 (종료일 - 시작일)
    return (b - a).days
