"""
agents 패키지 초기화 모듈 (gRPC 버전)

이 패키지는 Azure AI Foundry 제안서 생성을 위한 다양한 AI 에이전트들을 포함합니다.

주요 변경사항:
- MessageBus/Agent 베이스 의존성을 제거했습니다.
- gRPC 서버가 각 클래스를 직접 인스턴스화하여 메서드를 호출합니다.
- 각 에이전트는 독립적으로 동작하며 OpenAI API를 사용합니다.

포함된 에이전트:
- CompetitorSearchAgent: 경쟁사 분석
- CustomerProfileAgent: 고객 프로필 분석
- FeatureSuggestionAgent: 기능 제안
- RevenueModelAgent: 수익모델 도출
- FormatterAgent: 한국어 포맷팅
- MarkdownWriterAgent: 마크다운 작성
"""

__all__ = [
    "CompetitorSearchAgent",
    "CustomerProfileAgent",
    "FeatureSuggestionAgent",
    "RevenueModelAgent",
    "FormatterAgent",
    "MarkdownWriterAgent",
]
