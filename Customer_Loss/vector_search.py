# =============================================
# vector_search.py — 벡터 기반 상품 카테고리 분류기
# =============================================
"""
키워드 기반 코사인 유사도를 사용한 상품 카테고리 자동 분류
상품명에서 키워드를 추출하여 미리 정의된 카테고리와 유사도를 계산

이 모듈은 상품명을 분석하여 적절한 카테고리를 자동으로 분류하는 기능을 제공합니다.
- 키워드 기반 벡터화: 상품명을 단어 빈도 벡터로 변환
- 코사인 유사도 계산: 카테고리별 키워드와의 유사도 측정
- 임계값 기반 분류: 유사도가 임계값 이상인 카테고리만 반환
"""
from __future__ import annotations
import math
from typing import List, Dict, Tuple
import re

class VectorBasedCategoryClassifier:
    """
    벡터 기반 상품 카테고리 분류기
    
    이 클래스는 상품명을 분석하여 적절한 카테고리를 자동으로 분류합니다.
    키워드 기반 벡터화와 코사인 유사도를 사용하여 정확한 분류를 수행합니다.
    """
    
    def __init__(self):
        """
        분류기 초기화 - 카테고리별 키워드 사전 설정
        
        각 카테고리별로 대표적인 키워드들을 미리 정의하여 
        상품명과의 유사도 계산에 사용합니다.
        """
        # 카테고리별 키워드 사전
        # 각 카테고리의 특징을 나타내는 대표 키워드들을 정의
        self.category_keywords: Dict[str, List[str]] = {
            "가전/주방": ["전기밥솥", "에어프라이어", "청소기", "전자레인지", "믹서기", "커피", "토스터", "전기포트"],
            "패션/의류": ["셔츠", "바지", "원피스", "코트", "자켓", "스니커즈", "구두", "가방"],
            "식품/건강": ["비타민", "오메가", "프로틴", "두유", "생수", "라면", "간식", "견과"],
            "디지털/모바일": ["스마트폰", "케이스", "충전기", "이어폰", "태블릿", "노트북", "키보드", "마우스"],
            "취미/레저": ["캠핑", "텐트", "등산", "요가", "보드", "낚시", "자전거", "피크닉"],
            "구독/쿠폰": ["구독", "정기배송", "쿠폰", "포인트", "멤버십"],
            "가구/인테리어": ["소파", "책상", "의자", "침대", "매트리스", "수납", "커튼", "조명"],
            "뷰티/케어": ["샴푸", "트리트먼트", "로션", "에센스", "마스크팩", "향수", "립", "쿠션"],
        }

    def _simple_tokenize(self, text: str) -> List[str]:
        """
        텍스트를 토큰으로 분리
        
        이 메서드는 상품명을 단어 단위로 분리하여 
        벡터화 과정에서 사용할 수 있는 토큰 리스트를 생성합니다.
        
        Args:
            text: 토큰화할 텍스트 (상품명)
            
        Returns:
            List[str]: 토큰 리스트 (영문, 숫자, 한글만 추출)
        """
        # 정규식을 사용하여 영문, 숫자, 한글만 추출
        # 특수문자와 공백은 제거하고 의미있는 단어만 추출
        return [t for t in re.findall(r"[A-Za-z0-9가-힣]+", text)]

    def _text_to_vec(self, text: str) -> Dict[str, int]:
        """
        텍스트를 단어 빈도 벡터로 변환
        
        이 메서드는 텍스트를 단어 빈도 기반의 벡터로 변환합니다.
        각 단어의 출현 빈도를 계산하여 딕셔너리 형태로 반환합니다.
        
        Args:
            text: 벡터화할 텍스트 (상품명 또는 카테고리 키워드)
            
        Returns:
            Dict[str, int]: 단어별 빈도 딕셔너리 (단어: 빈도수)
        """
        # 단어 빈도를 저장할 딕셔너리 초기화
        vec: Dict[str, int] = {}
        
        # 토큰화된 단어들의 빈도 계산
        for t in self._simple_tokenize(text):
            vec[t] = vec.get(t, 0) + 1
        
        return vec

    def _cosine(self, a: Dict[str, int], b: Dict[str, int]) -> float:
        """
        두 벡터 간의 코사인 유사도 계산
        
        이 메서드는 두 단어 빈도 벡터 간의 코사인 유사도를 계산합니다.
        코사인 유사도는 벡터 간의 각도를 측정하여 유사성을 나타냅니다.
        
        Args:
            a: 첫 번째 벡터 (단어:빈도)
            b: 두 번째 벡터 (단어:빈도)
            
        Returns:
            float: 코사인 유사도 (0.0 ~ 1.0, 1.0에 가까울수록 유사)
        """
        # 빈 벡터인 경우 유사도 0 반환
        if not a or not b:
            return 0.0
        
        # 내적 계산 (벡터 a와 b의 내적)
        # 공통 단어들의 빈도를 곱한 값들의 합
        dot = sum(v * b.get(k, 0) for k, v in a.items())
        
        # 벡터 크기 계산 (각 벡터의 유클리드 노름)
        na = math.sqrt(sum(v*v for v in a.values()))
        nb = math.sqrt(sum(v*v for v in b.values()))
        
        # 벡터 크기가 0인 경우 유사도 0 반환
        if na == 0 or nb == 0:
            return 0.0
        
        # 코사인 유사도 = 내적 / (벡터크기1 * 벡터크기2)
        # 이 값은 -1과 1 사이의 값이며, 1에 가까울수록 유사함을 의미
        return dot / (na * nb)

    def classify_product(self, name: str, threshold: float = 0.2) -> List[Tuple[str, float]]:
        """
        상품명을 기반으로 카테고리 분류
        
        이 메서드는 상품명을 분석하여 가장 적합한 카테고리를 찾습니다.
        각 카테고리와의 유사도를 계산하고, 임계값 이상인 카테고리들을 반환합니다.
        
        Args:
            name: 분류할 상품명
            threshold: 유사도 임계값 (이 값 이상인 카테고리만 반환, 기본값: 0.2)
            
        Returns:
            List[Tuple[str, float]]: (카테고리명, 유사도) 튜플 리스트 (유사도 내림차순)
        """
        # 상품명을 벡터로 변환
        name_vec = self._text_to_vec(name)
        results: List[Tuple[str, float]] = []
        
        # 각 카테고리와 유사도 계산
        for cat, kws in self.category_keywords.items():
            # 카테고리 키워드들을 하나의 텍스트로 결합하여 벡터화
            kw_vec = self._text_to_vec(" ".join(kws))
            
            # 상품명 벡터와 카테고리 키워드 벡터 간의 코사인 유사도 계산
            sim = self._cosine(name_vec, kw_vec)
            
            # 임계값 이상인 카테고리만 결과에 포함
            if sim >= threshold:
                results.append((cat, sim))
        
        # 유사도 기준으로 내림차순 정렬 (가장 유사한 카테고리부터)
        results.sort(key=lambda x: x[1], reverse=True)
        return results
