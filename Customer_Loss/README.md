# Customer_Loss 프로젝트

## 프로젝트 파일 구조

```
Customer_Loss/ (고객 손실)
├── agents/ (에이전트 모듈들)
│   ├── __init__.py (에이전트 패키지 초기화)
│   ├── feature_engineer.py (특징 엔지니어링 에이전트)
│   ├── predictor.py (이탈 예측 에이전트)
│   ├── explainer.py (예측 결과 설명 에이전트)
│   ├── recommender_core.py (추천 시스템 핵심 로직)
│   ├── recommender_collaborative.py (협업 필터링 추천)
│   ├── recommender_content.py (콘텐츠 기반 추천)
│   ├── hybrid_aggregator.py (하이브리드 추천 집계)
│   ├── llm_recommender.py (LLM 기반 추천 보조 에이전트)
│   ├── similar_customers.py (유사 고객 탐색 에이전트)
│   └── grpc_utils.py (gRPC 유틸리티 함수들)
├── churn_mcp.py (MCP 서버 - 외부 도구 연동 및 에이전트 조율)
├── utils.py (공통 유틸리티 함수들)
├── vector_search.py (벡터 기반 상품 분류기)
├── churn.proto (Protocol Buffers 정의)
├── churn_pb2.py (Protocol Buffers 생성 파일)
├── churn_pb2_grpc.py (gRPC 서비스 스텁)
├── pyproject.toml (프로젝트 설정)
├── requirements.txt (의존성 패키지)
├── start_agents.ps1 (에이전트 시작 스크립트)
├── stop_agents.ps1 (에이전트 종료 스크립트)
├── README.md (프로젝트 문서)
└── customer.txt (고객 데이터 파일)
```

Feature (6101) ← 최하위 레벨
    ↑
    ├─ Predictor (6102)
    │     ↑
    │     └─ Explainer (6103)
    │
    ├─ Similar (6107)
    │
    ├─ Collab (6104) ←→ Content (6105) [양방향 직접 통신]
    │     │              │
    │     └──────────────┘
    │           (서로 직접 호출)