# formatter_agent.py
# 포맷터 에이전트 모듈
# 영문 텍스트를 한국어로 번역하고 전문적인 문서 형식으로 포맷팅합니다.
from __future__ import annotations
import os
import grpc
import asyncio

from openai import AsyncOpenAI

import agents_pb2
import agents_pb2_grpc


class FormatterAgent:
    """텍스트 번역 및 포맷팅을 수행하는 에이전트 클래스"""
    def __init__(self):
        # 환경변수에서 OpenAI API 키를 가져옴
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            # API 키가 있으면 AsyncOpenAI 클라이언트 초기화
            self.client = AsyncOpenAI(api_key=api_key)
        else:
            # API 키가 없으면 None으로 설정 (LLM 없이 동작 가능)
            self.client = None
    
    async def run(self, text: str):
        """영문 텍스트를 한국어로 번역 및 포맷팅"""
        try:
            # LLM이 없으면 기본 메시지 반환
            if not self.client:
                return f"[KO 변환됨]\n{text}\n\n(LLM 번역을 위해 OPENAI_API_KEY 환경변수를 설정해주세요)"
            
            # 이미 한국어인지 간단히 체크 (한국어 문자가 포함되어 있으면 번역 스킵)
            # 유니코드 범위 AC00(가) ~ D7A3(힣)로 한국어 문자 확인
            has_korean = any('\uAC00' <= char <= '\uD7A3' for char in text[:100])
            
            if has_korean:
                # 이미 한국어인 경우 포맷팅만 수행
                # 문장 구조와 표현을 개선하여 더 읽기 쉽고 전문적으로 정리
                prompt = f"""다음 텍스트를 더 읽기 쉽고 전문적인 한국어로 정리해주세요. 
내용은 그대로 유지하되, 문장 구조와 표현을 개선해주세요:

{text}"""
            else:
                # 영어인 경우 번역 및 포맷팅
                # 자연스러운 한국어로 번역하고 전문적인 비즈니스 문서 형식으로 정리
                prompt = f"""다음 영어 텍스트를 자연스러운 한국어로 번역하고, 전문적인 비즈니스 문서 형식으로 정리해주세요:

{text}"""

            # OpenAI API를 통해 번역 및 포맷팅 요청
            # gpt-5.2 모델 사용, temperature 0.3으로 일관성 있는 번역 제공
            response = await self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "당신은 전문 번역가이자 문서 편집자입니다. 정확하고 자연스러운 한국어로 번역하고 포맷팅합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
            )
            
            # 응답에서 포맷팅된 텍스트 추출
            formatted_text = response.choices[0].message.content
            return formatted_text
            
        except Exception as e:
            # 예외 발생 시 원본 텍스트와 함께 오류 메시지 반환
            return f"[번역 오류: {str(e)}]\n{text}"


class FormatterService(agents_pb2_grpc.FormatterServiceServicer):
    """gRPC 서비스 - 포맷터 서비스 구현"""
    def __init__(self):
        # FormatterAgent 인스턴스 생성
        self.agent = FormatterAgent()
        # 다음 에이전트 주소 설정
        self.customer_addr = os.getenv("CUSTOMER_ADDR", "localhost:6002")

    async def _call_customer(self, profiles_path: str, question: str, competitor: str):
        """CustomerAgent 호출"""
        try:
            async with grpc.aio.insecure_channel(self.customer_addr) as ch:
                stub = agents_pb2_grpc.CustomerServiceStub(ch)
                return await stub.Profile(
                    agents_pb2.CustomerProfileRequest(
                        profiles_path=profiles_path,
                        question=question,
                        competitor=competitor
                    )
                )
        except Exception as e:
            return agents_pb2.CustomerProfileResponse(ok=False, error=str(e))

    async def FormatKo(self, req, ctx):
        """gRPC FormatKo 메서드 - 한국어 포맷팅 요청 처리"""
        try:
            # 에이전트의 run 메서드 호출하여 번역 및 포맷팅 수행
            out = await self.agent.run(req.text)
            if not out:
                return agents_pb2.FormatKoResponse(ok=False, error="포맷팅 실패")
            
            # CustomerAgent를 직접 호출 (competitor 정보 전달)
            if req.profiles_path and req.question:
                customer_result = await self._call_customer(req.profiles_path, req.question, out)
                if customer_result.ok:
                    # CustomerAgent가 다음 에이전트를 호출하도록 처리됨
                    return agents_pb2.FormatKoResponse(ok=True, value=out)
                else:
                    return agents_pb2.FormatKoResponse(ok=False, error=f"CustomerAgent 호출 실패: {customer_result.error}")
            else:
                # CustomerAgent 호출 없이 포맷팅 결과만 반환
                return agents_pb2.FormatKoResponse(ok=True, value=out)
        except Exception as e:
            # 실패 응답 반환 (오류 메시지 포함)
            return agents_pb2.FormatKoResponse(ok=False, error=str(e))


async def serve(port: int = None):
    """gRPC 서버 시작 함수"""
    # 포트 설정: 인자로 전달된 포트 또는 환경변수 또는 기본값 6005
    port = port or int(os.getenv("FORMATTER_PORT", "6005"))
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # FormatterService를 서버에 등록
    agents_pb2_grpc.add_FormatterServiceServicer_to_server(
        FormatterService(), server
    )
    # 서버를 지정된 포트에 바인딩 (모든 인터페이스에서 접근 가능)
    server.add_insecure_port(f"0.0.0.0:{port}")
    # 서버 시작
    await server.start()
    print(f"[FormatterService] running {port}")
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
