"""
고객 분석 시스템의 에이전트 모듈 (gRPC 전환)
- message_bus 의존 제거
- 각 에이전트는 메서드 호출로만 사용

이탈 예측 파이프라인:
- FeatureEngineerAgent: 고객 데이터 특징 추출
- HeuristicPredictorAgent: 이탈 확률 예측
- ExplainerAgent: 예측 결과 설명

추천 시스템 파이프라인:
- CollaborativeRecommenderAgent: 협업 필터링
- ContentRecommenderAgent: 콘텐츠 기반
- HybridAggregatorAgent: 하이브리드 집계
- SimilarCustomersAgent: 유사 고객 탐색
"""


__all__ = [
    "FeatureEngineerAgent", "HeuristicPredictorAgent", "ExplainerAgent",
    "CollaborativeRecommenderAgent", "ContentRecommenderAgent",
    "HybridAggregatorAgent", "SimilarCustomersAgent",
]
