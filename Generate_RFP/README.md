# Generate_RFP

RFP(Request for Proposal, 제안요청서) PDF 문서를 자동 분석하여 제안서 목차와 자사 대응표(Compliance Matrix)를 생성하는 AI 기반 시스템입니다.

## 프로젝트 구조

```
Generate_RFP/
├── main.py                          # MCP 서버 (툴 진입점)
├── grpc_client.py                   # gRPC 클라이언트 구현
├── grpc_server.py                   # gRPC 서버 래퍼 클래스
├── rfp.proto                        # Protocol Buffers 정의 파일
├── rfp_pb2.py                       # protobuf 메시지 (자동 생성)
├── rfp_pb2_grpc.py                  # protobuf 서비스 (자동 생성)
├── pyproject.toml                   # 프로젝트 설정 및 의존성
├── README.md                        # 프로젝트 문서
│
├── agents/                          # AI 에이전트 모듈
│   ├── rfp_outline_agent.py         # 목차 추출 에이전트
│   └── compliance_matrix_agent.py   # 자사 대응표 생성 에이전트
│
├── RFP.pdf                          # 입력 RFP 문서 (예시)
└── RFP.rfp_compliance.xlsx         # 생성된 자사 대응표 (출력)
```

## 파일 설명

### 핵심 모듈

- **main.py**: MCP 서버로서 RFP 분석을 위한 **툴 진입점** 역할을 합니다. 오케스트레이터가 아니라, MCP 클라이언트(예: Cursor)와의 연동을 제공하며, `rfp_orchestrator` 툴을 통해 입력(pdf_path 등)을 검증한 뒤 **ComplianceMatrixAgent**를 gRPC로 한 번 호출합니다. 실제 분석 프로세스의 조율(목차 추출 → 요구사항 추출 → 자사 대응표 생성)은 ComplianceMatrixAgent가 수행하며, 해당 에이전트가 필요 시 OutlineAgent를 gRPC로 직접 호출하는 **에이전트 간 직접 통신(A2A)** 구조입니다.

- **grpc_client.py**: gRPC 클라이언트 구현체로, 에이전트 간 직접 통신을 담당합니다. 지연 초기화 패턴을 사용하여 효율적인 연결을 관리합니다.

- **grpc_server.py**: 에이전트 간 통신을 위한 공통 메시징 레이어를 제공합니다. gRPC 기반 비동기 처리, 오류 처리(잘못된 payload·미등록 토픽·핸들러 예외), JSON 페이로드 전달, 토픽 기반 라우팅을 포함하며, **GrpcServer** 클래스는 각 에이전트를 독립적인 gRPC 서버로 구동할 수 있게 하는 핵심 인프라 역할을 담당합니다. (타임아웃은 **grpc_client.py**에서 설정합니다.)

- **rfp.proto**: Protocol Buffers 정의 파일로, gRPC 서비스와 메시지 타입을 정의합니다.

### AI 에이전트

- **agents/rfp_outline_agent.py (Outline Agent)**: RFP PDF로부터 제안서 목차를 생성하는 역할을 담당합니다. PyMuPDF(fitz)로 텍스트를 추출한 뒤 OpenAI API(모델: **gpt-5.2**)로 1~3차 목차를 도출하며, API 사용이 불가한 경우 휴리스틱 알고리즘으로 폴백합니다. 독립적인 gRPC 서버로 동작하며 **outline.extract** 토픽을 통해 호출됩니다. 입력값은 PDF 경로(pdf_path)와 보정 힌트(hints), 출력값은 구조화된 목차 배열(outline)입니다.

- **agents/compliance_matrix_agent.py (Compliance Matrix Agent)**: RFP 요구사항을 분석해 자사 대응표(Compliance Matrix)를 생성합니다. OpenAI API(모델: **gpt-5.2**)로 요구사항을 추출·분류하고, pandas로 엑셀 형식의 매트릭스(요구사항·중요도·자사 대응·비고)로 정리합니다. 목차 대비 누락된 요구사항을 자동 탐지하는 **커버리지 갭 분석**을 수행해 결과(coverage_gaps)에 포함합니다. 페이로드에 목차(outline)가 없을 때 gRPC로 **Outline Agent**를 호출해 목차 정보를 동적으로 가져오며, **compliance.build** 토픽을 통해 독립적인 gRPC 서버로 실행됩니다 (에이전트 간 직접 통신, A2A).

### 생성 파일

- **rfp_pb2.py**, **rfp_pb2_grpc.py**: `rfp.proto`에서 자동 생성된 Python 파일입니다.

### 설정 파일

- **pyproject.toml**: 프로젝트 메타데이터, 의존성, 빌드 설정을 포함합니다.

## 사용 방법

1. 환경 변수 설정:
   - `OPENAI_API_KEY`: OpenAI API 키
   - `RFP_OUTLINE_ADDR`: Outline Agent gRPC 주소 (기본값: 127.0.0.1:6051)
   - `RFP_COMPLIANCE_ADDR`: Compliance Agent gRPC 주소 (기본값: 127.0.0.1:6052)

2. 에이전트 서버 실행 (두 에이전트 모두 별도 터미널에서 실행):
   ```bash
   # 터미널 1: Outline Agent 서버 실행 (6051 포트)
   python agents/rfp_outline_agent.py
   
   # 터미널 2: Compliance Matrix Agent 서버 실행 (6052 포트)
   python agents/compliance_matrix_agent.py
   ```

3. CLI로 RFP 분석 수행 (새 터미널에서):
   ```bash
   # 기본 사용 (RFP.pdf 사용)
   python main.py
   
   # PDF 파일 지정
   python main.py path/to/RFP.pdf
   
   # 출력 파일 지정
   python main.py path/to/RFP.pdf --out output.xlsx
   
   # 목차 추출 힌트 제공
   python main.py path/to/RFP.pdf --hints "특정 섹션에 주의"
   ```

## 아키텍처

이 프로젝트는 **에이전트 간 직접 통신(A2A: Agent-to-Agent)** 기반으로 설계되었습니다:

```
main.py (CLI)
    ↓ gRPC (6052 포트)
ComplianceMatrixAgent (서버)
    ↓ gRPC (6051 포트)
OutlineAgent (서버)
```

**gRPC 통신 레이어(grpc_client.py, grpc_server.py)**  
MCP 서버(툴 진입점)에서 에이전트로의 호출과 에이전트 간 호출을 처리합니다. **GrpcClient**는 지연 초기화 방식으로 채널·스텁을 효율적으로 관리하고, **RfpServicer**는 JSON 페이로드를 파싱해 토픽별 핸들러를 실행한 뒤 결과를 반환합니다. 전체 구조는 비동기 통신(grpc.aio)을 기반으로 하며, 클라이언트·서버 모두에서 안정적인 예외 처리를 지원합니다. (이 아키텍처에는 오케스트레이터가 없으며, 에이전트 간 직접 통신(A2A)으로 동작합니다.)

**특징:**
- **Orchestrator 없음**: 중앙 오케스트레이터 없이 에이전트들이 직접 통신
- **두 에이전트 모두 서버로 실행**: 각각 독립적인 프로세스에서 gRPC 서버로 실행
  - OutlineAgent: 6051 포트
  - ComplianceMatrixAgent: 6052 포트
- **gRPC 통신**: 에이전트 간 비동기 gRPC 통신으로 느슨한 결합 유지
- **분산 실행**: 각 에이전트를 별도 프로세스로 실행하여 격리 및 확장성 확보

**컴플라이언스 매트릭스 생성 워크플로우**

1. **main.py (CLI/툴 진입점)** → `client.request("compliance.build", payload)` 로 ComplianceMatrixAgent 호출  
2. **ComplianceMatrixAgent** (compliance.build) 수신 → **outline이 없을 때만** OutlineAgent 호출(목차 변환)  
3. **OutlineAgent** (outline.extract) → PDF에서 목차 추출 후 반환  
4. **ComplianceMatrixAgent** → 요구사항 추출, Excel 저장, 커버리지 갭 분석  
5. **출력** → `RFP.rfp_compliance.xlsx` + 커버리지 갭 정보(coverage_gaps)

## 출력

- **RFP.rfp_compliance.xlsx**: 자사 대응표 Excel 파일
  - 요구사항
  - 중요도 (High/Medium/Low)
  - 자사 대응
  - 비고

