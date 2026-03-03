# Search FactCheck ContentsFilter

AI 응답의 정확성과 안전성을 보장하기 위한 팩트체크 및 콘텐츠 필터링 기능을 제공하는 Model Context Protocol (MCP) 서버입니다.

## 프로젝트 구조

```
Search_FactCheck_ContentsFilter/
├── __pycache__/              # Python 바이트코드 캐시
├── agents/                   # AI 에이전트 모듈
│   ├── __pycache__/         # 에이전트 모듈 캐시
│   ├── enhanced_content_filter.py    # 고급 콘텐츠 필터
│   ├── fact_checker.py               # 팩트체크 에이전트
│   ├── final_response.py             # 최종 응답 생성 에이전트
│   ├── hallucination_filter.py       # 환각 필터 에이전트
│   ├── question_refiner.py           # 질문 정제 에이전트
│   └── responder.py                  # 응답 생성 에이전트
├── agents.proto              # gRPC 서비스 정의
├── agents_pb2.py             # 생성된 gRPC Python 코드
├── agents_pb2_grpc.py        # 생성된 gRPC 서비스 스텁
├── mcp_server.py             # MCP 서버
├── pyproject.toml            # 프로젝트 설정 및 의존성
├── query.py                  # MCP 클라이언트 테스트
└── README.md                 # 프로젝트 개요
```

## 주요 기능

- **질문 정제**: 사용자 질문을 핵심 개념에 집중하도록 정제
- **응답 생성**: OpenAI의 LLM을 사용하여 응답 생성
- **팩트체크**: Tavily 검색을 사용하여 정보 검증
- **콘텐츠 필터링**: 환각 현상 및 부적절한 콘텐츠 감지
- **최종 응답**: 모든 결과를 안전하고 팩트체크된 응답으로 통합

## 설치 방법

1. **의존성 설치**:
   ```bash
   pip install -r requirements.txt
   ```

2. **API 키 발급**:
   - **OpenAI API Key**: [OpenAI Platform](https://platform.openai.com/api-keys)에서 발급
   - **Tavily API Key**: [Tavily](https://tavily.com/)에서 발급

3. **환경 변수 설정**:
   - `.env.example`을 `.env`로 복사
   - `.env` 파일에 API 키 추가:
     ```
     OPENAI_API_KEY=your_openai_api_key_here
     TAVILY_API_KEY=your_tavily_api_key_here
     ```

4. **서버 실행**:
   ```bash
   python mcp_server.py
   ```

## MCP 도구

- `ask`: 질문에서 안전한 응답까지의 전체 파이프라인 실행

## 사용 방법

이 MCP 서버는 Cursor와 같은 MCP 호환 클라이언트에서 사용하도록 설계되었습니다. MCP 클라이언트 설정에서 이 서버를 구성하여 팩트체크 및 콘텐츠 필터링 도구에 접근할 수 있습니다.

## 아키텍처

Search_FactCheck_ContentsFilter의 주요 컴포넌트는 MCP 서버, 여러 gRPC 기반 에이전트, 그리고 최종 응답 조합 단계로 구성됩니다. MCP 서버(mcp_server.py)는 외부 클라이언트(Cursor 등)와 연결되는 진입점으로, 모든 처리를 단일 엔드포인트인 `ask` 도구를 통해 수행하도록 설계되어 있습니다. 이 도구는 질문을 입력받아 Refiner의 Process 메서드를 호출하여 전체 파이프라인을 시작합니다. 실제 오케스트레이션은 에이전트 간 직접 통신으로 이루어지며, MCP 서버는 단순히 진입점 역할만 담당합니다. 에이전트들은 각각 독립적인 gRPC 서버로 실행되며, 서로 직접 gRPC 호출을 통해 통신합니다.

Question Refiner(agents/question_refiner.py)는 사용자의 질문을 핵심 정보 중심으로 단순화하고 불필요한 표현을 제거하여, 이후 단계에서 처리하기 쉬운 형태로 변환합니다. Refiner는 오케스트레이터 역할을 담당하며, Process 메서드에서 전체 파이프라인을 조율합니다. 정제된 질문은 Responder와 Fact Checker에 병렬로 전달되며, 두 에이전트의 결과를 받아 HalluService의 AnalyzeAndFinalize를 호출합니다.

Responder(agents/responder.py)는 OpenAI GPT-5.1 모델을 활용해 사실 기반의 초안 응답을 생성합니다. temperature를 0.3으로 설정해 안정성을 확보하며, 생성된 응답은 Hallucination Filter로 전달되어 추가 검증과 환각 감지에 활용됩니다. 환각이 감지된 경우 HalluService에 의해 Revise 메서드가 호출되어 답변을 더 보수적으로 수정합니다.

Fact Checker(agents/fact_checker.py)는 Tavily Search API를 사용하여 정제된 질문에 대한 실시간 검증을 수행합니다. 검색된 문서에서 추출한 핵심 사실, 출처 URL, 검증 상태(verified / unverifiable)를 생성해 Refiner에 반환함으로써 응답의 신뢰성을 보완합니다. Fact Checker는 MCP 서버가 아닌 Refiner에 직접 결과를 반환합니다.

Hallucination Filter(agents/hallucination_filter.py)는 Responder가 생성한 초안 응답이 사실과 불일치하거나 위험 패턴을 포함하는지 평가합니다. Enhanced Content Filter를 내부 모듈로 사용하여 안전성을 검사하며, GPT 기반 판단을 결합하여 환각 가능성을 단계별로 평가합니다. 문제가 감지되면 Responder 서비스를 직접 호출하여 자동으로 응답을 수정합니다. 최종적으로 HalluService는 Finalizer를 직접 호출하여 최종 응답을 생성합니다.

Enhanced Content Filter(agents/enhanced_content_filter.py)는 독립적인 gRPC 서버가 아닌 HalluService 내부에서 사용되는 모듈입니다. 정규식 기반의 빠른 스캔과 LLM 기반의 정밀 분석이 결합된 하이브리드 필터링을 수행합니다. 자해, 자살, 폭력, 극단주의 등 고위험 요소를 카테고리별로 분류하고, 위험 콘텐츠가 감지되면 안전한 대체 응답을 제시합니다. 한국어 사용자에게 적합한 안전 메시지 템플릿을 제공하며, LLM 호출이 실패했을 때 지수 백오프 방식으로 재시도하여 안정성을 높입니다.

마지막으로 Final Response(agents/final_response.py)는 HalluService에 의해 호출됩니다. HalluResponse와 FactCheckResponse를 종합하여 최종 답변을 구성합니다. 최종 출력에는 신뢰도 평가 메시지(검증 상태 기반), 환각 수준 정보, 참고 소스 URL이 포함됩니다.

이 시스템의 특징은 중앙 오케스트레이터 없이 각 에이전트가 필요한 다른 에이전트를 직접 gRPC로 호출하는 에이전트 간 직접 통신 구조입니다. Refiner가 Responder와 FactChecker를 병렬로 호출하여 성능을 최적화하며, 각 에이전트가 독립적인 gRPC 서버로 실행되어 확장성과 유지보수성을 향상시킵니다.

