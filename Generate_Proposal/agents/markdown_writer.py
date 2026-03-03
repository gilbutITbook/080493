# markdown_writer.py
# 마크다운 작성 에이전트 모듈
# 제안서 내용을 마크다운 형식으로 작성하고 파일로 저장합니다.
from __future__ import annotations
import os
import grpc
import asyncio
import re
from pathlib import Path
from datetime import datetime

import agents_pb2
import agents_pb2_grpc


class MarkdownWriterAgent:
    """마크다운 파일 작성 및 저장을 수행하는 에이전트 클래스"""
    def write(self, company, market, question, customer, features, revenue, competitor):
        """제안서 내용을 마크다운 형식으로 작성"""
        # 회사, 시장, 고객 인사이트, 기능 제안, 수익모델, 경쟁사 분석을 포함한 마크다운 템플릿
        return f"# 제안서\n\n## 회사: {company}\n## 시장: {market}\n\n### 고객 인사이트\n{customer}\n\n### 기능 제안\n{features}\n\n### 수익모델\n{revenue}\n\n### 경쟁사 분석\n{competitor}\n"

    def save(self, path: str, text: str):
        """마크다운 텍스트를 파일로 저장"""
        # 저장 경로의 부모 디렉토리가 없으면 생성
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # UTF-8 인코딩으로 마크다운 파일 저장
        Path(path).write_text(text, encoding="utf-8")
        return path


class WriterService(agents_pb2_grpc.WriterServiceServicer):
    """gRPC 서비스 - 마크다운 작성 서비스 구현"""
    def __init__(self):
        # MarkdownWriterAgent 인스턴스 생성
        self.agent = MarkdownWriterAgent()

    async def PersistMd(self, req, ctx):
        """gRPC PersistMd 메서드 - 마크다운 파일 저장 요청 처리"""
        try:
            # 에이전트의 write 메서드 호출하여 마크다운 내용 생성
            md = self.agent.write(
                req.company,
                req.market,
                req.question,
                req.customer,
                req.features,
                req.revenue,
                req.competitor,
            )
            # 파일명 설정: 요청에 파일명이 있으면 사용, 없으면 환경변수 확인, 둘 다 없으면 동적 생성
            if req.filename and req.filename.strip():
                filename = req.filename.strip()
            else:
                # 환경변수에서 파일명 확인
                env_filename = os.getenv("OUTPUT_FILENAME")
                if env_filename and env_filename.strip():
                    filename = env_filename.strip()
                else:
                    # 동적 파일명 생성: 질문 기반 또는 타임스탬프 기반
                    if req.question and req.question.strip():
                        # 질문에서 키워드 추출 (한글, 영문, 숫자만 허용)
                        question_clean = re.sub(r'[^\w\s가-힣]', '', req.question.strip())
                        # 첫 30자만 사용하고 공백을 언더스코어로 변경
                        question_slug = re.sub(r'\s+', '_', question_clean[:30])
                        # 타임스탬프 추가 (초 단위)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"proposal_{question_slug}_{timestamp}.md"
                    else:
                        # 질문이 없으면 타임스탬프만 사용
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"proposal_{timestamp}.md"
            # 출력 디렉토리 설정: 요청에 디렉토리가 있으면 사용, 없으면 기본값 "outputs"
            out_dir = req.out_dir or "outputs"
            # 전체 파일 경로 구성
            path = os.path.join(out_dir, filename)
            # 에이전트의 save 메서드 호출하여 파일 저장
            saved = self.agent.save(path, md)
            # 성공 응답 반환 (저장된 파일 경로 포함)
            return agents_pb2.PersistMdResponse(ok=True, path=saved)
        except Exception as e:
            # 실패 응답 반환 (오류 메시지 포함)
            return agents_pb2.PersistMdResponse(ok=False, error=str(e))


async def serve(port: int = None):
    """gRPC 서버 시작 함수"""
    # 포트 설정: 인자로 전달된 포트 또는 환경변수 또는 기본값 6006
    port = port or int(os.getenv("WRITER_PORT", "6006"))
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # WriterService를 서버에 등록
    agents_pb2_grpc.add_WriterServiceServicer_to_server(
        WriterService(), server
    )
    # 서버를 지정된 포트에 바인딩 (모든 인터페이스에서 접근 가능)
    server.add_insecure_port(f"0.0.0.0:{port}")
    # 서버 시작
    await server.start()
    print(f"[WriterService] running {port}")
    # 서버 종료 대기
    await server.wait_for_termination()


# 직접 실행 시 gRPC 서버를 시작하는 진입점
if __name__ == "__main__":
    import argparse
    # 명령줄 인자 파서 생성
    p = argparse.ArgumentParser()
    # 포트 오버라이드 옵션 추가
    p.add_argument("--port", type=int)
    args = p.parse_args()
    # 서버 실행
    asyncio.run(serve(args.port))
