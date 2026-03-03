# customer_agent.py
# 고객 프로필 분석 에이전트 모듈
# CSV 파일로부터 고객 프로필을 읽고 LLM을 사용하여 분석합니다.
from __future__ import annotations
import os
import grpc
import asyncio
import csv
from typing import List, Dict

from openai import AsyncOpenAI

import agents_pb2
import agents_pb2_grpc


class CustomerProfileAgent:
    """고객 프로필을 분석하는 에이전트 클래스"""
    def __init__(self):
        # 환경변수에서 OpenAI API 키를 가져옴
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            # API 키가 있으면 AsyncOpenAI 클라이언트 초기화
            self.client = AsyncOpenAI(api_key=api_key)
        else:
            # API 키가 없으면 None으로 설정 (LLM 없이 동작 가능)
            self.client = None
    
    def _read_profiles(self, profiles_path: str) -> List[Dict[str, str]]:
        """고객 프로필 파일을 읽고 파싱"""
        profiles = []
        try:
            # UTF-8 인코딩으로 CSV 파일 열기
            with open(profiles_path, 'r', encoding='utf-8') as f:
                # CSV DictReader를 사용하여 딕셔너리 형태로 읽기
                reader = csv.DictReader(f)
                # 각 행을 프로필 리스트에 추가
                for row in reader:
                    # CSV 헤더와 값의 앞뒤 공백 제거
                    cleaned_row = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
                    profiles.append(cleaned_row)
        except Exception as e:
            # 파일 읽기 실패 시 예외 발생
            raise Exception(f"파일 읽기 실패: {e}")
        return profiles
    
    def _format_profiles_summary(self, profiles: List[Dict[str, str]]) -> str:
        """고객 프로필을 요약 형식으로 변환"""
        # 요약 라인 초기화 - 총 고객 수 표시
        summary_lines = [f"총 {len(profiles)}명의 고객 프로필"]
        
        # IT 지식별 분류
        # 각 프로필의 IT 지식 수준을 카운트
        it_levels = {}
        for profile in profiles:
            it_level = profile.get('IT지식', '알 수 없음')
            it_levels[it_level] = it_levels.get(it_level, 0) + 1
        
        # IT 지식별 분포를 요약에 추가
        summary_lines.append("\n[IT 지식 수준별 분포]")
        for level, count in it_levels.items():
            summary_lines.append(f"- {level}: {count}명")
        
        # 직무별 분류
        # 각 프로필의 직무를 카운트
        departments = {}
        for profile in profiles:
            dept = profile.get('직무', '알 수 없음')
            departments[dept] = departments.get(dept, 0) + 1
        
        # 직무별 분포를 요약에 추가 (인원수 기준 내림차순 정렬)
        summary_lines.append("\n[직무별 분포]")
        for dept, count in sorted(departments.items(), key=lambda x: x[1], reverse=True):
            summary_lines.append(f"- {dept}: {count}명")
        
        # 주요 고민
        # 각 프로필의 주요 고민을 카운트
        concerns = {}
        for profile in profiles:
            concern = profile.get('주요고민', '알 수 없음')
            concerns[concern] = concerns.get(concern, 0) + 1
        
        # 주요 고민을 요약에 추가 (상위 5개만, 인원수 기준 내림차순)
        summary_lines.append("\n[주요 고민]")
        for concern, count in sorted(concerns.items(), key=lambda x: x[1], reverse=True)[:5]:
            summary_lines.append(f"- {concern}: {count}명")
        
        # 모든 요약 라인을 개행문자로 결합하여 반환
        return "\n".join(summary_lines)
    
    async def analyze(self, profiles_path: str, question: str):
        """고객 프로필을 읽고 LLM으로 분석"""
        try:
            # 파일 읽기 - CSV 파일에서 고객 프로필 데이터 로드
            profiles = self._read_profiles(profiles_path)
            if not profiles:
                # 프로필이 없으면 오류 반환
                return {"ok": False, "error": "고객 프로필이 없습니다"}
            
            # 프로필 요약 생성 - 통계 정보 추출
            profiles_summary = self._format_profiles_summary(profiles)
            
            # LLM이 없으면 요약만 반환
            if not self.client:
                return {
                    "ok": True,
                    "summary": f"{profiles_summary}\n\n질문: {question}\n\n(LLM 분석을 위해 OPENAI_API_KEY 환경변수를 설정해주세요)"
                }
            
            # LLM으로 분석 - 고객 프로필과 질문을 바탕으로 맞춤형 분석 요청
            prompt = f"""다음은 고객 프로필 정보입니다:

{profiles_summary}

질문: {question}

위 고객 프로필을 분석하고 질문에 대한 상세한 답변을 한국어로 작성해주세요. 
각 고객의 직무, 직책, 주요 고민, IT 지식 수준, 기타 사항을 종합적으로 고려하여 
실용적이고 구체적인 제안을 제시해주세요."""

            # OpenAI API를 통해 고객 프로필 분석 요청
            # gpt-5.2 모델 사용, temperature 0.7로 창의성과 일관성의 균형 유지
            response = await self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "당신은 고객 프로필을 분석하고 맞춤형 제안을 제공하는 전문 컨설턴트입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            
            # 응답에서 분석 결과 추출
            analysis = response.choices[0].message.content
            
            # 프로필 요약과 분석 결과를 결합하여 반환
            return {
                "ok": True,
                "summary": f"{profiles_summary}\n\n## 분석 결과\n\n{analysis}"
            }
            
        except Exception as e:
            # 예외 발생 시 오류 정보 반환
            return {"ok": False, "error": str(e)}


class CustomerService(agents_pb2_grpc.CustomerServiceServicer):
    """gRPC 서비스 - 고객 프로필 분석 서비스 구현"""
    def __init__(self):
        # CustomerProfileAgent 인스턴스 생성
        self.agent = CustomerProfileAgent()
        # 다음 에이전트 주소 설정
        self.feature_addr = os.getenv("FEATURE_ADDR", "localhost:6003")

    async def _call_feature(self, competitor: str, customer: str, company: str, market: str, question: str):
        """FeatureAgent 호출"""
        try:
            async with grpc.aio.insecure_channel(self.feature_addr) as ch:
                stub = agents_pb2_grpc.FeatureServiceStub(ch)
                return await stub.Propose(
                    agents_pb2.FeatureProposeRequest(
                        competitor=competitor,
                        customer=customer,
                        company=company,
                        market=market,
                        question=question
                    )
                )
        except Exception as e:
            return agents_pb2.FeatureProposeResponse(ok=False, error=str(e))

    async def Profile(self, req, ctx):
        """gRPC Profile 메서드 - 고객 프로필 분석 요청 처리"""
        try:
            # 에이전트의 analyze 메서드 호출하여 고객 프로필 분석 수행
            out = await self.agent.analyze(req.profiles_path, req.question)
            if not out.get("ok"):
                return agents_pb2.CustomerProfileResponse(ok=False, error=out.get("error", "고객 분석 실패"))
            
            customer_value = out["summary"]
            
            # FeatureAgent를 직접 호출 (competitor 정보 전달)
            competitor = getattr(req, 'competitor', '') or ""
            company = os.getenv("COMPANY", "Azure AI Foundry")
            market = os.getenv("MARKET", "FSI")
            question = req.question
            
            if competitor:
                feature_result = await self._call_feature(competitor, customer_value, company, market, question)
                if feature_result.ok:
                    # FeatureAgent가 다음 에이전트를 호출하도록 처리됨
                    return agents_pb2.CustomerProfileResponse(ok=True, value=customer_value)
                else:
                    return agents_pb2.CustomerProfileResponse(ok=False, error=f"FeatureAgent 호출 실패: {feature_result.error}")
            else:
                # FeatureAgent 호출 없이 고객 분석 결과만 반환
                return agents_pb2.CustomerProfileResponse(ok=True, value=customer_value)
        except Exception as e:
            # 실패 응답 반환 (오류 메시지 포함)
            return agents_pb2.CustomerProfileResponse(ok=False, error=str(e))


async def serve(port: int = None):
    """gRPC 서버 시작 함수"""
    # 포트 설정: 인자로 전달된 포트 또는 환경변수 또는 기본값 6002
    port = port or int(os.getenv("CUSTOMER_PORT", "6002"))
    # 비동기 gRPC 서버 생성
    server = grpc.aio.server()
    # CustomerService를 서버에 등록
    agents_pb2_grpc.add_CustomerServiceServicer_to_server(
        CustomerService(), server
    )
    # 서버를 지정된 포트에 바인딩 (모든 인터페이스에서 접근 가능)
    server.add_insecure_port(f"0.0.0.0:{port}")
    # 서버 시작
    await server.start()
    print(f"[CustomerService] running {port}")
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
