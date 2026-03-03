# ===== 향상된 콘텐츠 필터 =====
# 사용자 입력과 AI 응답에 대한 고급 안전성 검사를 수행하는 모듈입니다.
# 정규식 기반 빠른 필터링과 LLM 기반 정밀 분석을 조합하여 위험한 콘텐츠를 감지합니다.

# 필요한 라이브러리들을 import
import os, re, json, sys, asyncio, random  # 시스템, 정규식, JSON, 비동기 처리, 랜덤
from typing import Dict, List, Optional, Tuple  # 타입 힌트
from openai import AsyncOpenAI  # OpenAI API 클라이언트
from openai import APIError, RateLimitError, APITimeoutError  # OpenAI 에러 타입들

# 에러 로깅 함수
# 디버깅과 모니터링을 위해 에러를 표준 에러 출력으로 전송
def _elog(msg: str):
    sys.stderr.write(str(msg) + "\n"); sys.stderr.flush()

# 텍스트 길이 제한 함수 - 너무 긴 텍스트를 안전하게 절단
# LLM API 호출 시 토큰 제한을 고려하여 텍스트를 안전하게 잘라냄
def _truncate(text: str, max_len: int) -> str:
    if text is None:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + " ...[truncated]"  # 잘린 부분임을 표시

# 텍스트 정규화 함수 - null 문자 제거 및 공백 정리
# 입력 텍스트를 안전하게 정리하여 처리
def _normalize(text: str) -> str:
    return (text or "").replace("\x00", "").strip()  # null 문자 제거 및 공백 정리

# 향상된 콘텐츠 필터 클래스
class EnhancedContentFilter:
    """
    사용자 입력/모델 응답에 대한 경량 위험도 점검(정규식) → 필요 시 LLM 정밀 판정.
    
    주요 기능:
    - 퍼블릭 API:
      * analyze_text(text) -> Dict   # 분석 결과 JSON
      * filter_content(text) -> str  # 차단/대체 문구 or 원문 반환
    
    설계 포인트:
      * 빠른 정규식 패스(자살/폭력 등)로 즉시 차단
      * LLM 호출은 백오프 포함, JSON 실패 시 폴백
      * 너무 긴 텍스트는 안전하게 절단
    """
    def __init__(
        self,
        model: str = "gpt-5.2",
        max_text_length: int = 4000,
        quick_patterns: Optional[Dict[str, List[str]]] = None,
        llm_timeout: float = 20.0,
        max_retries: int = 3,
        retry_base_delay: float = 0.6,
    ):
        # OpenAI API 키 검증
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        # OpenAI 클라이언트 초기화
        try:
            self.client = AsyncOpenAI(api_key=api_key)
        except Exception as e:
            _elog(f"[EnhancedContentFilter] OpenAI client init error: {e}")
            raise

        # 설정값 저장
        self.model = model  # 사용할 GPT 모델
        self.max_text_length = max_text_length  # 최대 텍스트 길이
        self.llm_timeout = llm_timeout  # LLM 호출 타임아웃
        self.max_retries = max_retries  # 최대 재시도 횟수
        self.retry_base_delay = retry_base_delay  # 재시도 기본 지연 시간

        # 기본 정규식 패턴 정의 (고위험 카테고리)
        # 자살, 자해, 폭력 등 위험한 내용을 빠르게 감지하기 위한 패턴들
        default_patterns = {
            "suicide": [
                r"자살", r"죽고\s*싶다", r"목숨을\s*끊", r"극단적\s*선택", r"스스로\s*목숨",
            ],
            "self_harm": [
                r"자해", r"칼로\s*베", r"상처\s*내는\s*법",
            ],
            "overdose": [
                r"치사량", r"과다\s*복용", r"몇\s*알.*죽",
            ],
            "violence": [
                r"사람을\s*죽이", r"살인", r"폭탄\s*만드는\s*법", r"총기\s*제작",
            ],
            "extremism": [
                r"테러\s*방법", r"폭력\s*조장",
            ],
        }
        
        # 사용자 지정 패턴이 있으면 기본 패턴과 병합
        # 사용자가 추가 패턴을 제공한 경우 기본 패턴에 추가
        if quick_patterns:
            for k, arr in quick_patterns.items():
                default_patterns.setdefault(k, []).extend(arr)
        
        # 정규식 패턴들을 컴파일하여 저장 (대소문자 무시)
        # 성능을 위해 정규식을 미리 컴파일하여 저장
        self.quick_patterns_compiled: Dict[str, List[re.Pattern]] = {
            k: [re.compile(p, re.IGNORECASE) for p in v]
            for k, v in default_patterns.items()
        }

    # ===== Public API =====
    
    # 텍스트 분석 메인 함수 - 정규식과 LLM 분석을 순차적으로 실행
    # 1단계: 빠른 정규식 검사, 2단계: LLM 정밀 분석
    async def analyze_text(self, text: str) -> Dict:
        text = _normalize(text)  # 텍스트 정규화
        # 1단계: 빠른 정규식 패턴 검사
        qp = self._quick_pattern_check(text)
        if qp.get("should_block"):
            return qp  # 고위험 패턴 발견 시 즉시 반환
        # 2단계: LLM 기반 정밀 판정
        return await self._llm_based_analysis(text)

    # 콘텐츠 필터링 함수 - 차단 시 안전한 대체 응답 반환
    # 분석 결과에 따라 안전한 대체 응답을 반환하거나 원문을 반환
    async def filter_content(self, text: str) -> str:
        """차단 판단 시 안전 대체 응답 반환, 아니면 원문 반환"""
        analysis = await self.analyze_text(text)
        if analysis.get("should_block"):
            return self._safe_response(analysis)
        return text

    # ===== Internal: Quick Pattern =====
    
    # 정규식 기반 빠른 위험 패턴 검사
    # 미리 정의된 위험 패턴들을 빠르게 검사하여 고위험 콘텐츠를 즉시 차단
    def _quick_pattern_check(self, text: str) -> Dict:
        flagged = []
        # 각 카테고리별 패턴 검사
        for cat, pats in self.quick_patterns_compiled.items():
            for pat in pats:
                if pat.search(text):  # 패턴 매치 발견
                    flagged.append({"category": cat, "pattern": pat.pattern})
                    # 고위험 패턴 발견 시 즉시 차단
                    return {
                        "risk_level": "high",
                        "risk_score": 18,
                        "detected_patterns": flagged,
                        "should_block": True,
                        "safety_message": "위험한 내용이 감지되어 답변할 수 없습니다.",
                        "analysis_method": "quick_pattern",
                        "risk_categories": list({f["category"] for f in flagged}),
                        "reason": "high_risk_keyword_detected"
                    }
        # 위험 패턴이 발견되지 않은 경우
        return {
            "should_block": False,
            "analysis_method": "quick_pattern_passed",
            "risk_level": "unknown",
            "risk_score": 0,
            "risk_categories": [],
            "detected_patterns": [],
        }

    # ===== Internal: LLM Analysis with retries =====
    
    # LLM을 사용한 정밀 위험도 분석 (재시도 로직 포함)
    # 정규식으로 감지되지 않은 미묘한 위험 요소들을 LLM으로 분석
    async def _llm_based_analysis(self, text: str) -> Dict:
        safe_text = _truncate(text, self.max_text_length)  # 텍스트 길이 제한
        
        # LLM 분석을 위한 프롬프트 구성
        # GPT가 위험한 콘텐츠를 감지하도록 하는 프롬프트
        prompt = f"""
다음 텍스트가 자해, 자살, 폭력, 테러, 불법무기제작, 과다복용, 극단주의 선동 등 위험한 내용을 포함하는지 한국어로 분석하세요.
가능하면 과도 차단을 피하되, 실제 위험 신호에는 보수적으로 대응하세요.

텍스트:
\"\"\"{safe_text}\"\"\"

JSON만 반환:
{{
  "risk_level": "low|medium|high",
  "risk_score": 0-20,
  "should_block": true|false,
  "risk_categories": ["..."],
  "reason": "...",
  "safety_message": "...",
  "suggestions": ["..."]
}}
""".strip()

        last_error: Optional[Exception] = None
        # 최대 재시도 횟수만큼 시도
        # API 오류나 네트워크 문제로 실패할 경우 재시도
        for attempt in range(1, self.max_retries + 1):
            try:
                # OpenAI API 호출 (JSON 응답 형식 지정)
                res = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0,
                        response_format={"type": "json_object"},
                    ),
                    timeout=self.llm_timeout,
                )

                # 응답 텍스트 추출 (다양한 응답 형식 지원)
                # OpenAI API 응답에서 텍스트를 추출하는 다양한 방법 시도
                raw = None
                try:
                    raw = getattr(res.choices[0].message, "content", None)
                except Exception:
                    raw = None
                if not raw:
                    raw = getattr(res.choices[0], "text", None) or getattr(res, "text", None) or ""

                # JSON 파싱 시도
                # GPT 응답을 JSON으로 파싱하여 구조화된 데이터로 변환
                try:
                    data = json.loads(raw or "{}")
                except Exception:
                    _elog("[EnhancedContentFilter] JSON parse failed; returning fallback analysis")
                    return {
                        "risk_level": "unknown",
                        "risk_score": 0,
                        "should_block": False,
                        "risk_categories": [],
                        "reason": "json_parse_error",
                        "safety_message": "분석 결과 파싱 실패",
                        "suggestions": [],
                        "analysis_method": "llm_based_parse_error",
                    }

                # 응답 데이터 보강 및 기본값 설정
                # JSON 파싱 성공 시 필요한 필드들을 보강하고 기본값 설정
                data["analysis_method"] = "llm_based"
                data.setdefault(
                    "detected_patterns",
                    [{"category": c} for c in data.get("risk_categories", [])],
                )
                data.setdefault("risk_level", "unknown")
                data.setdefault("risk_score", 0)
                data.setdefault("should_block", False)
                data.setdefault("safety_message", "안전하지 않을 수 있는 주제입니다. 다른 주제로 이야기해 주세요.")
                data.setdefault("suggestions", [])
                return data

            except (RateLimitError, APITimeoutError) as e:
                # Rate limit나 타임아웃 에러는 재시도
                last_error = e
                # 지수 백오프 + 약간의 지터로 재시도 간격 조정
                # 재시도 간격을 점진적으로 늘려서 API 부하를 줄임
                delay = self.retry_base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.2)
                await asyncio.sleep(delay)
            except APIError as e:
                # API 에러는 재시도하지 않음
                last_error = e
                break
            except Exception as e:
                # 기타 에러는 재시도하지 않음
                last_error = e
                break

        # 모든 재시도 실패 시 폴백 결과 반환
        _elog(f"[EnhancedContentFilter] LLM call error after retries: {last_error}")
        return self._fallback(safe_text)

    # ===== Fallback =====
    
    # LLM 분석 실패 시 사용하는 폴백 결과
    # 모든 재시도가 실패한 경우 안전한 기본값을 반환
    def _fallback(self, text: str) -> Dict:
        return {
            "risk_level": "unknown",
            "risk_score": 0,
            "should_block": False,
            "risk_categories": [],
            "reason": "analysis_error",
            "safety_message": "분석 오류",
            "suggestions": ["잠시 후 다시 시도해 주세요"],
            "analysis_method": "fallback",
        }

    # ===== Safe response builder =====
    
    # 위험한 콘텐츠가 감지된 경우 사용자에게 보여줄 안전한 대체 응답 생성
    # 위험도에 따라 적절한 안전 메시지를 생성
    def _safe_response(self, analysis: Dict) -> str:
        # 고위험인 경우 한국 내 도움 리소스 제공
        # 자살이나 자해 관련 고위험 콘텐츠인 경우 전문가 도움 리소스 제공
        if analysis.get("risk_level") == "high" or analysis.get("should_block"):
            return (
                "죄송합니다. 이 내용엔 도움을 드릴 수 없습니다. "
                "자해나 자살에 대한 생각이 있다면 전문가의 도움을 받으세요.\n"
                "자살예방상담전화: 1393 / 정신건강상담전화: 1577-0199 / 응급: 119"
            )
        # 일반적인 안전 메시지 반환
        return analysis.get("safety_message") or "안전하지 않을 수 있는 주제입니다. 다른 주제로 이야기해 주세요."
