# =============================================
# agents/recommender_core.py
# =============================================
"""
추천 시스템의 핵심 로직을 담당하는 공통 유틸리티 클래스
협업 필터링, 콘텐츠 기반 추천, 유사 고객 탐색의 공통 기능 제공
"""
from __future__ import annotations
from typing import Dict, Any, List, Tuple
import math, re


class RecommenderCore:
    """추천 시스템의 핵심 로직을 담당하는 공통 유틸리티 클래스

    협업 필터링, 콘텐츠 기반 추천, 유사 고객 탐색의 공통 기능을 제공
    고객-상품 행렬, 유사도 계산, 추천 알고리즘 등을 포함
    """

    def __init__(self):
        """추천 핵심 로직 초기화"""
        self.customer_ids: List[str] = []  # 고객 ID 리스트
        self.product_ids: List[str] = []  # 상품 ID 리스트
        self.customer_product_matrix: List[List[int]] = []  # 고객-상품 행렬
        self.product_popularity: Dict[str, int] = {}  # 상품 인기도
        self.product_features: Dict[str, Dict[str, Any]] = {}  # 상품 특징
        self.customer_similarities: List[List[float]] = []  # 고객 유사도 행렬
        self.product_similarities: List[List[float]] = []  # 상품 유사도 행렬

    # ---------- 데이터 구성 메서드들 ----------
    def build_customer_product_matrix(self, all_customers: List[Dict[str, Any]]):
        """고객-상품 행렬 구축

        고객과 상품 간의 구매 관계를 이진 행렬로 표현합니다.
        행렬의 각 요소는 고객이 해당 상품을 구매했는지(1) 여부(0)를 나타냅니다.
        이 행렬은 협업 필터링과 콘텐츠 기반 추천의 기반이 됩니다.

        Args:
            all_customers: 모든 고객의 특징 데이터 (고객ID, 원본_구매이력 포함)
        """
        # 고객별 구매 상품 리스트를 저장할 딕셔너리
        cust_to_products: Dict[str, List[str]] = {}
        # 전체 상품 집합 (중복 제거용)
        prod_set = set()

        # 각 고객의 구매 이력에서 상품명 추출
        for row in all_customers:
            cid = str(row.get("고객ID", "")).strip()  # 고객 ID 추출
            hist = str(row.get("원본_구매이력", "")).strip()  # 구매 이력 문자열
            if not cid:
                continue  # 고객 ID가 없으면 스킵

            prods: List[str] = []
            # 구매 이력을 파싱하여 상품명 추출
            # 쉼표, 줄바꿈, 세미콜론으로 구분된 각 항목 처리
            for chunk in re.split(r"[,\n;]+", hist):
                chunk = (chunk or "").strip()
                if not chunk:
                    continue
                # 날짜 패턴 찾기 (YYYY-MM-DD 형식)
                # 예: "2023-01-01 에스프레소머신" -> 날짜와 상품명 분리
                m = re.search(r"\d{4}-\d{2}-\d{2}", chunk)
                # 날짜 이후 부분을 상품명으로 사용 (날짜가 없으면 전체를 상품명으로)
                name = (chunk[m.end():] if m else chunk).strip()
                if name:
                    prods.append(name)
                    prod_set.add(name)  # 전체 상품 집합에 추가
            # 중복 제거 (dict.fromkeys는 순서를 유지하면서 중복 제거)
            cust_to_products[cid] = list(dict.fromkeys(prods))

        # 고객과 상품 ID 정렬 (일관된 인덱싱을 위해)
        self.customer_ids = sorted(cust_to_products.keys())
        self.product_ids = sorted(prod_set)
        # 인덱스 매핑 딕셔너리 생성 (빠른 조회를 위해)
        idx_c = {c: i for i, c in enumerate(self.customer_ids)}  # 고객ID -> 행 인덱스
        idx_p = {p: i for i, p in enumerate(self.product_ids)}  # 상품ID -> 열 인덱스

        # 고객-상품 행렬 초기화 및 채우기
        # 행: 고객, 열: 상품, 값: 1(구매함) 또는 0(구매안함)
        self.customer_product_matrix = [
            [0] * len(self.product_ids) for _ in self.customer_ids
        ]
        # 상품 인기도 초기화 (각 상품을 구매한 고객 수)
        self.product_popularity = {p: 0 for p in self.product_ids}
        
        # 각 고객의 구매 상품을 행렬에 반영
        for c, products in cust_to_products.items():
            ci = idx_c[c]  # 고객의 행 인덱스
            for p in products:
                pi = idx_p[p]  # 상품의 열 인덱스
                self.customer_product_matrix[ci][pi] = 1  # 구매 표시
                self.product_popularity[p] += 1  # 인기도 증가

    def build_product_features(self):
        """상품 특징 정보 구축

        각 상품에 대해 카테고리, 가격, 설명 등의 메타데이터를 생성합니다.
        실제 상품 데이터베이스가 없는 경우를 대비하여 상품명 기반으로 추정합니다.
        이 메타데이터는 추천 결과에 포함되어 사용자에게 표시됩니다.
        """

        def guess_category(name: str) -> str:
            """상품명을 기반으로 카테고리 추정
            
            상품명에 포함된 키워드를 기반으로 카테고리를 자동 분류합니다.
            키워드 매칭 방식으로 간단하고 빠르게 카테고리를 결정합니다.
            
            Args:
                name: 상품명
                
            Returns:
                str: 추정된 카테고리명 (매칭 실패 시 "기타")
            """
            name_l = name.lower()  # 대소문자 구분 없이 비교하기 위해 소문자 변환
            # 카테고리별 키워드 규칙 정의
            # 각 카테고리는 대표 키워드 리스트를 가지고 있음
            rules = [
                (
                    "가전/주방",
                    ["밥솥", "에어프라이어", "청소기", "전자레인지", "믹서", "커피", "토스터", "포트"],
                ),
                ("패션/의류", ["셔츠", "바지", "원피스", "코트", "자켓", "스니커즈", "구두", "가방"]),
                ("식품/건강", ["비타민", "오메가", "프로틴", "두유", "생수", "라면", "간식", "견과"]),
                (
                    "디지털/모바일",
                    ["폰", "스마트폰", "케이스", "충전기", "이어폰", "태블릿", "노트북", "키보드", "마우스"],
                ),
                ("취미/레저", ["캠핑", "텐트", "등산", "요가", "보드", "낚시", "자전거", "피크닉"]),
                ("가구/인테리어", ["소파", "책상", "의자", "침대", "매트리스", "수납", "커튼", "조명"]),
                ("뷰티/케어", ["샴푸", "트리트먼트", "로션", "에센스", "마스크", "향수", "립", "쿠션"]),
                ("구독/쿠폰", ["구독", "정기배송", "쿠폰", "멤버십", "포인트"]),
            ]
            # 각 카테고리의 키워드 중 하나라도 상품명에 포함되면 해당 카테고리 반환
            for cat, keys in rules:
                if any(k in name_l for k in keys):
                    return cat
            return "기타"  # 매칭되는 카테고리가 없으면 "기타"

        def pseudo_price(name: str) -> int:
            """상품명을 기반으로 가격 생성 (해시 기반)
            
            실제 가격 데이터가 없으므로 상품명의 해시값을 사용하여 
            일관된 가격을 생성합니다. 같은 상품명은 항상 같은 가격을 반환합니다.
            
            Args:
                name: 상품명
                
            Returns:
                int: 생성된 가격 (10,000원 ~ 100,000원 범위, 100원 단위)
            """
            # 상품명의 해시값을 사용하여 10,000 ~ 100,000 범위의 값 생성
            base = abs(hash(name)) % 90_000 + 10_000
            return int(round(base, -2))  # 100원 단위로 반올림

        # 각 상품에 대한 특징 정보 생성
        self.product_features = {}
        for p in self.product_ids:
            cat = guess_category(p)  # 카테고리 추정
            self.product_features[p] = {
                "name": p,  # 상품명
                "category": cat,  # 추정된 카테고리
                "price": pseudo_price(p),  # 생성된 가격
                "description": f"{cat} 카테고리의 인기 상품",  # 기본 설명
            }

    # ---------- 유사도 계산 메서드들 ----------
    def _cosine_matrix(self, mat: List[List[int]]) -> List[List[float]]:
        """행렬의 코사인 유사도 행렬 계산
        
        입력 행렬의 각 행(벡터) 간의 코사인 유사도를 계산합니다.
        코사인 유사도는 두 벡터 간의 각도를 측정하여 유사성을 나타냅니다.
        값의 범위는 -1 ~ 1이며, 1에 가까울수록 유사함을 의미합니다.
        (이진 행렬의 경우 0 ~ 1 범위)
        
        Args:
            mat: 입력 행렬 (각 행은 하나의 벡터를 나타냄)
            
        Returns:
            List[List[float]]: 유사도 행렬 (N x N, N은 행의 개수)
        """
        if not mat:
            return []
        n_rows = len(mat)  # 행의 개수
        
        # 각 행(벡터)의 유클리드 노름(크기) 계산
        # 노름 = sqrt(sum(v^2)) - 벡터의 길이
        norms = [math.sqrt(sum(v * v for v in row)) for row in mat]
        
        # 유사도 행렬 초기화 (N x N)
        sims = [[0.0] * n_rows for _ in range(n_rows)]

        # 모든 행 쌍에 대해 코사인 유사도 계산
        for i in range(n_rows):
            for j in range(n_rows):
                # 벡터 크기가 0이면 유사도 0 (빈 벡터)
                if norms[i] == 0 or norms[j] == 0:
                    sims[i][j] = 0.0
                    continue
                # 내적 계산: 두 벡터의 내적 = sum(a[i] * b[i])
                dot = sum(mat[i][k] * mat[j][k] for k in range(len(mat[i])))
                # 코사인 유사도 = 내적 / (벡터1의 크기 * 벡터2의 크기)
                sims[i][j] = dot / (norms[i] * norms[j])
        return sims

    def calculate_customer_similarities(self):
        """고객 간 유사도 계산
        
        고객-상품 행렬을 기반으로 고객 간의 구매 패턴 유사도를 계산합니다.
        협업 필터링에서 유사한 고객을 찾는 데 사용됩니다.
        """
        # 고객-상품 행렬의 각 행(고객) 간 코사인 유사도 계산
        self.customer_similarities = self._cosine_matrix(self.customer_product_matrix)

    def calculate_product_similarities(self):
        """상품 간 유사도 계산
        
        고객-상품 행렬을 전치하여 상품 간의 유사도를 계산합니다.
        콘텐츠 기반 추천에서 유사한 상품을 찾는 데 사용됩니다.
        """
        # 행렬 전치: 행과 열을 바꿔서 상품-고객 행렬로 변환
        # zip(*matrix)는 행렬을 전치하는 Python 관용구
        transposed = (
            [list(x) for x in zip(*self.customer_product_matrix)]
            if self.customer_product_matrix
            else []
        )
        # 전치된 행렬의 각 행(상품) 간 코사인 유사도 계산
        self.product_similarities = self._cosine_matrix(transposed)

    # ---------- 공통 fallback: 인기 상품 ----------
    def _fallback_popular_products(
        self, bought: set, top_n: int
    ) -> List[Tuple[str, float]]:
        """추천이 완전히 비었을 때 사용할 인기 상품 기반 fallback
        
        협업 필터링이나 콘텐츠 기반 추천이 결과를 반환하지 못할 때
        전체 고객 중에서 가장 많이 구매된 상품을 추천합니다.
        이는 콜드 스타트 문제를 완화하는 데 도움이 됩니다.
        
        Args:
            bought: 고객이 이미 구매한 상품 집합 (제외 대상)
            top_n: 반환할 상품 개수
            
        Returns:
            List[Tuple[str, float]]: (상품명, 인기도 점수) 튜플 리스트
        """
        # 상품 인기도 기준으로 내림차순 정렬
        ranked = sorted(
            self.product_popularity.items(), key=lambda x: x[1], reverse=True
        )
        # 이미 구매한 상품은 제외하고 점수를 float로 변환
        ranked = [(p, float(pop)) for p, pop in ranked if p not in bought]
        return ranked[:top_n]  # 상위 top_n개만 반환

    # ---------- 추천 알고리즘 메서드들 ----------
    def recommend_collaborative(
        self, customer_id: str, top_n: int
    ) -> List[Tuple[str, float]]:
        """협업 필터링 기반 상품 추천
        
        유사한 고객들이 구매한 상품을 추천합니다.
        알고리즘:
        1. 대상 고객과 유사한 고객들을 찾음
        2. 유사 고객들이 구매한 상품에 유사도 점수를 가중치로 부여
        3. 점수가 높은 상품을 추천
        
        Args:
            customer_id: 추천을 받을 고객 ID
            top_n: 반환할 추천 상품 개수
            
        Returns:
            List[Tuple[str, float]]: (상품명, 추천 점수) 튜플 리스트 (점수 내림차순)
        """
        if customer_id not in self.customer_ids:
            return []  # 고객이 존재하지 않으면 빈 리스트 반환

        ci = self.customer_ids.index(customer_id)  # 고객의 행 인덱스
        sims = self.customer_similarities[ci]  # 이 고객과 다른 모든 고객들의 유사도
        scores = [0.0] * len(self.product_ids)  # 각 상품의 추천 점수 초기화

        # 유사한 고객들이 구매한 상품에 유사도 점수를 가중치로 부여
        for other_idx, sim in enumerate(sims):
            if other_idx == ci or sim <= 0:
                continue  # 자기 자신이거나 유사도가 0 이하면 스킵
            # 유사 고객이 구매한 각 상품에 유사도 점수 추가
            for pi, has in enumerate(self.customer_product_matrix[other_idx]):
                if has:  # 유사 고객이 구매한 상품이면
                    scores[pi] += sim  # 유사도 점수를 가중치로 추가

        # 이미 구매한 상품 집합 생성 (제외 대상)
        bought = {
            self.product_ids[i]
            for i, v in enumerate(self.customer_product_matrix[ci])
            if v
        }
        
        # 모든 상품에 대해 (상품명, 점수) 튜플 생성
        ranked = [(self.product_ids[i], scores[i]) for i in range(len(self.product_ids))]
        # 이미 구매한 상품 제외하고, 점수가 0보다 큰 것만 선택
        ranked = [(p, s) for p, s in ranked if p not in bought and s > 0]
        # 점수 기준 내림차순 정렬
        ranked.sort(key=lambda x: x[1], reverse=True)

        # 협업 결과가 완전히 비면 인기 상품 fallback
        if not ranked:
            return self._fallback_popular_products(bought, top_n)

        return ranked[:top_n]  # 상위 top_n개 반환

    def recommend_content(
        self, customer_id: str, top_n: int
    ) -> List[Tuple[str, float]]:
        """콘텐츠 기반 상품 추천
        
        고객이 과거에 구매한 상품과 유사한 상품을 추천합니다.
        알고리즘:
        1. 고객이 구매한 상품들을 찾음
        2. 각 미구매 상품에 대해 구매한 상품들과의 최대 유사도를 계산
        3. 유사도가 높은 상품을 추천
        
        Args:
            customer_id: 추천을 받을 고객 ID
            top_n: 반환할 추천 상품 개수
            
        Returns:
            List[Tuple[str, float]]: (상품명, 유사도 점수) 튜플 리스트 (점수 내림차순)
        """
        if customer_id not in self.customer_ids:
            return []  # 고객이 존재하지 않으면 빈 리스트 반환

        ci = self.customer_ids.index(customer_id)  # 고객의 행 인덱스
        # 고객이 구매한 상품들의 열 인덱스 리스트
        bought_indices = [
            i for i, v in enumerate(self.customer_product_matrix[ci]) if v
        ]

        # 이미 구매한 상품 집합 생성 (제외 대상)
        bought = {self.product_ids[i] for i in bought_indices}

        # 구매 이력이 없는 경우 → 인기 상품 fallback
        if not bought_indices:
            return self._fallback_popular_products(bought, top_n)

        # 각 상품에 대한 유사도 점수 초기화
        scores = [0.0] * len(self.product_ids)
        for pi in range(len(self.product_ids)):
            if pi in bought_indices:
                continue  # 이미 구매한 상품은 스킵
            # 구매한 상품들과의 최대 유사도 계산
            # 최대 유사도를 사용하는 이유: 하나라도 매우 유사하면 추천 가치가 있음
            max_sim = 0.0
            for bi in bought_indices:
                max_sim = max(max_sim, self.product_similarities[pi][bi])
            scores[pi] = max_sim  # 최대 유사도를 점수로 사용

        # 점수가 0보다 큰 상품만 선택하여 (상품명, 점수) 튜플 생성
        ranked = [
            (self.product_ids[i], scores[i])
            for i in range(len(self.product_ids))
            if scores[i] > 0
        ]
        # 점수 기준 내림차순 정렬
        ranked.sort(key=lambda x: x[1], reverse=True)

        # 유사도 기반 결과가 하나도 없으면 → 인기 상품 기반 fallback
        if not ranked:
            return self._fallback_popular_products(bought, top_n)

        return ranked[:top_n]  # 상위 top_n개 반환

    # ---------- 유사 고객 탐색 ----------
    def similar_customers(self, customer_id: str, top_n: int) -> List[Tuple[str, float]]:
        """유사 고객 탐색
        
        대상 고객과 구매 패턴이 유사한 고객들을 찾습니다.
        고객 간 유사도 행렬을 사용하여 코사인 유사도가 높은 고객들을 반환합니다.
        
        Args:
            customer_id: 유사 고객을 찾을 대상 고객 ID
            top_n: 반환할 유사 고객 개수
            
        Returns:
            List[Tuple[str, float]]: (고객ID, 유사도 점수) 튜플 리스트 (점수 내림차순)
        """
        if customer_id not in self.customer_ids:
            return []  # 고객이 존재하지 않으면 빈 리스트 반환

        ci = self.customer_ids.index(customer_id)  # 고객의 행 인덱스
        sims = self.customer_similarities[ci]  # 이 고객과 다른 모든 고객들의 유사도

        # 자기 자신을 제외한 모든 고객과의 유사도 쌍 생성
        pairs = [
            (other_id, float(sims[i]))  # (고객ID, 유사도 점수)
            for i, other_id in enumerate(self.customer_ids)
            if i != ci  # 자기 자신 제외
        ]
        # 유사도 점수 기준 내림차순 정렬
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs[:top_n]  # 상위 top_n개 반환
