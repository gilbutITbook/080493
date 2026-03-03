# VOC Improve 프로젝트

VOC(Voice of Customer) 분석 시스템 - 고객 불만사항 분석 및 정책 개선안 생성

## 프로젝트 구조

```
VOC_Improve/
│
├── main.py                    # MCP 서버 메인 진입점
├── grpc_server.py            # gRPC 기반 클라이언트 (A2A VOC Orchestrator)
├── voc.proto                 # Protocol Buffers 정의 파일
├── voc_pb2.py                # Protocol Buffers 생성 파일 (Python)
├── voc_pb2_grpc.py           # gRPC 서비스 생성 파일 (Python)
├── voc.csv                   # VOC 데이터 파일
├── pyproject.toml            # 프로젝트 설정 파일
├── README.md                 # 프로젝트 문서
│
├── agents/                   # AI 에이전트 모듈
│   ├── __init__.py
│   ├── interpreter.py       # 자연어 질의 해석 에이전트
│   ├── retriever.py         # VOC 데이터 검색 에이전트
│   ├── summarizer.py        # VOC 요약 생성 에이전트
│   ├── improver.py          # 정책 개선안 생성 에이전트
│   ├── evaluator.py         # 결과 평가 에이전트
│   └── critic.py            # 결과 비판/개선 에이전트
│
├── llm_wrappers/            # LLM API 래퍼
│   ├── __init__.py
│   ├── openai_chat.py       # OpenAI API 래퍼
│   └── anthropic_chat.py    # Anthropic API 래퍼
│
└── utils/                   # 유틸리티 모듈
    ├── __init__.py
    ├── settings.py          # 설정 관리
    ├── tools.py             # MCP 도구 정의
    ├── json_utils.py        # JSON 처리 유틸리티
    └── utils.py             # 기타 유틸리티 함수
```

## 주요 기능

- **자연어 질의 분석**: 자연어 질의를 통한 VOC 분석 요청 처리
- **VOC 요약 생성**: 고객 불만사항을 분석하여 요약 생성
- **정책 개선안 생성**: VOC 분석 결과를 바탕으로 정책 개선안 제시
- **gRPC 통신**: A2A 시스템과의 gRPC 기반 통신
- **MCP 서버**: Claude Desktop/Cursor와의 통신을 위한 MCP 프로토콜 지원

## 기술 스택

- Python 3.13+
- gRPC
- Protocol Buffers
- OpenAI API / Anthropic API
- MCP (Model Context Protocol)

