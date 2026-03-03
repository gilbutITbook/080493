# A2A Orchestration (OpenAI + Claude)

Draft(OpenAI) → Critic(Claude) → Scoring(OpenAI) → Synthesis(Claude) 순차 체인으로
응답 품질을 높이는 오케스트레이션 예제입니다.

## 프로젝트 구조

```
Search_Multi_Model/
├── agents/                          # 에이전트 모듈
│   ├── __init__.py
│   ├── draft_agent.py              # Draft 에이전트 (OpenAI 사용)
│   ├── critic_agent.py             # Critic 에이전트 (Anthropic Claude 사용)
│   ├── scoring_agent.py            # Scoring 에이전트 (OpenAI 사용)
│   └── synth_agent.py              # Synthesis 에이전트 (Anthropic Claude 사용)
├── llm_wrappers/                    # LLM API 래퍼 모듈
│   ├── __init__.py
│   ├── openai_chat.py              # OpenAI Chat API 래퍼
│   └── anthropic_chat.py           # Anthropic Claude API 래퍼
├── config.py                        # 환경 변수 및 모델 설정
├── json_utils.py                    # JSON 파싱 유틸리티
├── metrics.py                       # 성능 모니터링 클래스
├── orchestrator.py                 # A2A 파이프라인 오케스트레이터
├── mcp_server.py                    # MCP (Model Context Protocol) 서버
├── a2a.proto                        # gRPC 프로토콜 정의
├── a2a_pb2.py                       # gRPC 프로토콜 Python 바인딩
├── a2a_pb2_grpc.py                  # gRPC 서비스 Python 바인딩
├── run_all_agents.ps1              # 모든 에이전트 서버 실행 스크립트
├── requirements.txt                 # Python 패키지 의존성
├── pyproject.toml                   # 프로젝트 설정
└── README.md                        # 프로젝트 문서
```

### 주요 파일 설명

- **orchestrator.py**: 전체 파이프라인을 조율하는 오케스트레이터. 각 에이전트를 gRPC로 호출하여 순차적으로 실행합니다.
- **agents/**: 각 에이전트는 독립적인 gRPC 서버로 동작하며, 별도 포트에서 실행됩니다.
  - `draft_agent.py`: 초안 생성 (포트 6001)
  - `critic_agent.py`: 초안 비평 및 개선 (포트 6002)
  - `scoring_agent.py`: 후보 평가 및 점수 매기기 (포트 6003)
  - `synth_agent.py`: 최종 답변 합성 (포트 6004)
- **llm_wrappers/**: 각 LLM 제공업체의 API를 통일된 인터페이스로 래핑합니다.
- **mcp_server.py**: MCP 프로토콜을 통해 A2A 파이프라인을 외부 도구로 노출합니다.

## 준비
- PowerShell (예)
$env:OPENAI_API_KEY="sk-..."
$env:ANTHROPIC_API_KEY="sk-ant-..."

## 실행
python -m a2a_orch.cli --query "생성형 AI 거버넌스 핵심 요소 요약" --debug --performance
