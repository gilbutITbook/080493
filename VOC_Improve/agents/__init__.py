# =============================================
# File: agents/__init__.py
# =============================================
# VOC 분석을 위한 AI 에이전트들의 패키지 초기화
#
# 이 패키지는 A2A(Agent-to-Agent) 아키텍처를 기반으로 한
# VOC 분석 시스템의 핵심 에이전트들을 정의합니다.
# 각 에이전트는 특정 역할을 담당하며, 서로 협력하여
# 고품질의 VOC 분석 결과를 생성합니다.
#
# 에이전트 구성(A2A 버전):
# - NLInterpreterAgent: 자연어 질의 해석 및 의도 파악
# - RetrieverAgent: VOC 데이터 검색 및 필터링
# - SummarizerAgent: VOC 데이터 요약(다중 후보/리파인 지원)
# - EvaluatorAgent: 후보 요약 교차 평가 및 승자 선택
# - CriticAgent: 요약/개선안 비평 및 수정 지시 생성
# - PolicyImproverAgent: 정책 개선안 생성(리파인 지원)

# ============ 패키지 공개 API 정의 ============
# 이 패키지에서 외부로 노출할 클래스 및 함수들을 정의합니다
# __all__ 리스트에 포함된 항목만 from agents import * 시 가져올 수 있습니다
__all__ = [
    "NLIntent",              # 자연어 의도 데이터 클래스
    "NLInterpreterAgent",    # 자연어 질의 해석 에이전트
    "RetrieverAgent",       # VOC 데이터 검색 에이전트
    "SummarizerAgent",      # 요약 생성 에이전트
    "EvaluatorAgent",       # 요약 평가 에이전트
    "CriticAgent",          # 요약/정책 비평 에이전트
    "PolicyImproverAgent",  # 정책 개선안 생성 에이전트
]
