# Azure AI Foundry 제안서 생성 시스템

gRPC 기반 AI 에이전트 오케스트레이션을 통한 Azure AI Foundry 제안서 자동 생성 시스템입니다.

## 개요

이 프로젝트는 고객 프로필과 질문을 바탕으로 Azure AI Foundry에 대한 맞춤형 제안서를 자동으로 생성하는 시스템입니다. 여러 AI 에이전트들이 gRPC를 통해 협력하여 경쟁사 분석, 고객 분석, 기능 제안, 수익모델 도출 등의 작업을 수행합니다.

## 주요 구성 요소

### 1. 오케스트레이터 (orchestrator.py)
- 전체 제안서 생성 파이프라인을 관리
- gRPC를 통해 각 AI 에이전트를 순차적으로 호출
- 최종 결과를 마크다운 파일로 저장

### 2. AI 에이전트들 (agents/)
- **CompetitorSearchAgent**: 특정 회사와 시장에 대한 경쟁사 분석
- **CustomerProfileAgent**: 고객 프로필 파일 기반 고객 분석
- **FeatureSuggestionAgent**: 경쟁사와 고객 분석을 바탕으로 한 기능 제안
- **RevenueModelAgent**: 제안된 기능들을 바탕으로 한 수익모델 도출
- **FormatterAgent**: 영문 분석 결과를 한국어로 번역 및 정리
- **MarkdownWriterAgent**: 모든 분석 결과를 마크다운 형식으로 저장

### 3. MCP 서버 (run.py)
- Model Context Protocol을 통한 외부 도구 호출 지원
- generate_proposal 도구 제공

## 설치 및 실행

### 1. 의존성 설치
```bash
pip install -e .
```

### 2. 환경 변수 설정
```bash
export OPENAI_API_KEY="your-openai-api-key"
export OUTPUT_DIR="outputs"  # 선택사항
```

### 3. 에이전트 실행
각 AI 에이전트를 독립 서버로 실행합니다:
```powershell
# PowerShell에서 실행
.\run_agents.ps1
```

또는 개별적으로 실행:
```bash
python -m agents.competitor_agent --port 6001
python -m agents.customer_agent --port 6002
python -m agents.feature_agent --port 6003
python -m agents.revenue_agent --port 6004
python -m agents.formatter_agent --port 6005
python -m agents.markdown_writer --port 6006
```

### 4. MCP 서버 실행
```bash
python run.py
```

### 5. 직접 실행 (오케스트레이터)
```bash
python orchestrator.py --company "Azure AI Foundry" --market "FSI" --profiles "customer_profiles.txt" --question "질문"
```

## 사용법

### MCP 도구 사용
```python
# generate_proposal 도구 호출
result = await generate_proposal(
    question="IT 지식이 전혀 없지만 비즈니스 임팩트를 중시하는 고객들에게 Azure AI Foundry를 제안하고 싶습니다.",
    profiles_path="customer_profiles.txt",
    company="Azure AI Foundry",
    market="FSI",
    save=True,
    out_dir="outputs",
    out_filename="custom_proposal.md"
)
```

### gRPC 서비스 직접 호출
각 AI 에이전트는 독립적인 gRPC 서비스로 제공되므로 필요에 따라 개별적으로 호출할 수 있습니다.

## 프로젝트 구조

```
Generate_Proposal/
├── orchestrator.py              # 메인 오케스트레이터
├── run.py                       # MCP 서버
├── run_agents.ps1               # 에이전트 실행 스크립트 (PowerShell)
├── agents/                      # AI 에이전트들
│   ├── __init__.py
│   ├── competitor_agent.py      # 경쟁사 분석
│   ├── customer_agent.py        # 고객 분석
│   ├── feature_agent.py         # 기능 제안
│   ├── revenue_agent.py         # 수익모델 도출
│   ├── formatter_agent.py       # 한국어 포맷팅
│   └── markdown_writer.py       # 마크다운 작성
├── agents.proto                 # gRPC 프로토콜 정의 파일
├── agents_pb2.py                # gRPC 프로토콜 생성 파일
├── agents_pb2_grpc.py           # gRPC 서비스 생성 파일
├── customer_profiles.txt         # 고객 프로필 데이터 (CSV 형식)
├── outputs/                     # 생성된 제안서 출력 디렉토리
│   ├── IT_지식_없음_고객_접근전략.md
│   └── Azure_AI_Foundry_제안서_AWS_비교_Revenue분석.md
├── logs/                        # 로그 파일 디렉토리
│   ├── competitor.log
│   ├── customer.log
│   ├── feature.log
│   ├── formatter.log
│   ├── revenue.log
│   └── writer.log
├── pyproject.toml               # 프로젝트 설정 및 의존성
└── README.md                    # 프로젝트 문서
```

## 생성되는 제안서 파일 구조

시스템이 생성하는 제안서 마크다운 파일은 다음과 같은 구조를 가집니다:

```
# 제안서

## 회사: [회사명]
## 시장: [시장명]

### 고객 인사이트
- 총 고객 프로필 수
- IT 지식 수준별 분포
- 직무별 분포
- 주요 고민 분류

## 분석 결과
- 질문에 대한 상세 분석
- 접근 전략 (5가지 주요 전략)
  1. 기초 교육 제공
  2. 맞춤형 자료 제공
  3. 멘토링 시스템 구축
  4. 사용자 친화적 도구 개발
  5. 정기적인 피드백 및 개선
- 결론

### 기능 제안
- 경쟁사 대비 Azure AI Foundry의 차별화된 기능
  - 통합 AI 생태계
  - 규정 준수 및 리스크 관리 모듈
  - 간편한 사용자 인터페이스(UI)
- 고객 니즈에 맞춘 맞춤형 기능 제안
- 각 기능의 비즈니스 가치 및 ROI
- 우선순위별 기능 로드맵
- 고객별 맞춤형 제안 전략
- 결론

### 수익모델
- 가격 정책 (구독 모델, 사용량 기반, 일회성 요금제)
- 각 기능별 수익 구조
- 예상 매출 및 수익성 분석
- ROI (투자 대비 수익) 계산
- 단계별 수익 목표
- 시장 규모 및 잠재 고객 수
- 경쟁사 대비 가격 경쟁력
- 고객 세그먼트별 수익 전략
- 결론

### 경쟁사 분석
- 주요 경쟁사 5곳 상세 분석
  - IBM Watson Financial Services
  - Google Cloud AI for Financial Services
  - Salesforce Financial Services Cloud
  - AWS Financial Services
  - SAS Financial Services Analytics
- 각 경쟁사별:
  - 회사명 및 주요 제품/서비스
  - 시장 점유율 및 위치
  - 주요 강점 및 차별점
  - Azure AI Foundry와의 비교
  - 시장 내 경쟁 우위/열위
- 전체 시장 경쟁력 결론
```

## 특징

- **모듈화된 설계**: 각 AI 에이전트가 독립적으로 동작
- **gRPC 기반 통신**: 확장 가능하고 효율적인 서비스 간 통신
- **MCP 지원**: 외부 도구와의 원활한 연동
- **한국어 지원**: 모든 결과를 한국어로 제공
- **폴백 메커니즘**: OpenAI API 키가 없을 경우 기본 결과 제공
- **원자적 파일 저장**: 데이터 무결성 보장

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

