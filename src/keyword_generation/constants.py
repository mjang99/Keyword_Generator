from __future__ import annotations

# Over-generation target: produce more candidates than the floor to absorb semantic dedup loss.
# The LLM dedup+quality pass (step B) will reduce this to the quality-passing subset.
# Raised for sparse live PDPs where quality-preserving dedup and hard-rule cleanup were leaving too few survivors.
INITIAL_GENERATION_TARGET: int = 160

POSITIVE_CATEGORY_TARGETS: dict[str, int] = {
    "brand": 10,
    "generic_category": 12,
    "feature_attribute": 18,
    "competitor_comparison": 8,
    "purchase_intent": 12,
    "long_tail": 16,
    "benefit_price": 6,
    "season_event": 6,
    "problem_solution": 12,
}

POSITIVE_CATEGORIES: tuple[str, ...] = tuple(POSITIVE_CATEGORY_TARGETS.keys())
NEGATIVE_CATEGORY = "negative"

NAVER_ALLOWED_MATCHES = {"완전일치", "확장소재", "제외키워드"}
GOOGLE_ALLOWED_MATCHES = {"exact", "phrase", "broad", "negative"}

PROMO_BANNED_TERMS = ("할인", "쿠폰", "최저가", "특가", "무료배송")
URGENCY_BANNED_TERMS = ("즉시출고", "당일배송", "재고임박", "마감임박", "품절임박")

NEGATIVE_KEYWORD_SEEDS = (
    "중고",
    "리퍼",
    "수리",
    "부품",
    "케이스만",
    "충전기만",
    "설명서",
    "매뉴얼",
    "다운로드",
    "무료체험",
)

SKINCARE_SEASON_SEEDS = ("겨울 보습", "환절기 보습", "야간 스킨케어", "여행용 보습", "건성 관리", "홈케어")
ELECTRONICS_SEASON_SEEDS = ("신학기 노트북", "업무용 노트북", "크리에이터 작업용", "출장용 노트북", "학생용 노트북", "연말 선물")
DEFAULT_SEASON_SEEDS = ("일상용", "선물용", "입문용", "추천", "비교", "사용 후기")
