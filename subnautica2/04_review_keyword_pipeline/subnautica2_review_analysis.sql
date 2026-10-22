-- ======================================================================
-- 서브노티카2 스팀 리뷰 키워드 분석 (순수 SQL 버전)
-- ======================================================================
-- [프로젝트 주도자 노트]
-- 부정 리뷰 중 특정 키워드(레비아탄, 튕김, 크래시, 어그로, 최적화)의
-- 언급 빈도를 계산함. Python(pandas)으로 만든 것과 동일한 로직을
-- 순수 SQL로 재구현함.
--
-- [중요 - 한국어 활용형 이슈 반영]
-- "튕김"이라는 완전한 단어로 검색하면 "자꾸 튕겨요" 같은 실제 리뷰
-- 문장을 놓침(활용형이 다르기 때문). 이 문제를 실제로 검증했던 것과
-- 동일하게, 여기서도 "튕"이라는 최소 어근 조각으로 검색함.
--
-- [추가 키워드 - 습성 도입 가설과 연결] "단조", "지루", "생태계"를 추가함.
-- 고철 운반형 습성 시뮬레이션 가설의 배경이 "초반 생태계·파밍이 단조롭게
-- 느껴질 수 있다"는 것이었는데, 실제 부정 리뷰에 이런 언급이 있는지
-- 확인하면 시뮬레이션(가상)과 별개로 실측 근거를 하나 더 확보할 수 있음.
-- "단조"/"지루"도 활용형 문제를 피하려 어근만 사용, "생태계"는 명사라
-- 그대로 사용. ("심심하다"는 "심심한 사과"처럼 다른 뜻으로도 쓰이는
-- 다의어라 오탐 위험이 있어 제외함)
--
-- 실행 방법: python3 run_subnautica2_sql.py
-- ======================================================================

-- ----------------------------------------------------------------------
-- 1단계: 전체 리뷰 요약 (긍정/부정 비율)
-- ----------------------------------------------------------------------
DROP VIEW IF EXISTS review_summary;
CREATE VIEW review_summary AS
SELECT
    COUNT(*)                                    AS 전체_리뷰수,
    SUM(CASE WHEN voted_up=1 THEN 1 ELSE 0 END) AS 긍정_리뷰수,
    SUM(CASE WHEN voted_up=0 THEN 1 ELSE 0 END) AS 부정_리뷰수,
    ROUND(100.0 * SUM(CASE WHEN voted_up=1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS 긍정비율_퍼센트
FROM reviews;

-- ----------------------------------------------------------------------
-- 2단계: 부정 리뷰 중 키워드별 언급 빈도
--        (활용형 문제 때문에 "튕김"이 아니라 "튕"으로 검색)
-- ----------------------------------------------------------------------
DROP VIEW IF EXISTS keyword_frequency;
CREATE VIEW keyword_frequency AS
SELECT
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%레비아탄%' THEN 1 ELSE 0 END) AS 레비아탄_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%튕%'      THEN 1 ELSE 0 END) AS 튕김_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%크래시%'  THEN 1 ELSE 0 END) AS 크래시_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%어그로%'  THEN 1 ELSE 0 END) AS 어그로_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%최적화%'  THEN 1 ELSE 0 END) AS 최적화_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%단조%'    THEN 1 ELSE 0 END) AS 단조_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%지루%'    THEN 1 ELSE 0 END) AS 지루_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%생태계%'  THEN 1 ELSE 0 END) AS 생태계_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%못죽%'    THEN 1 ELSE 0 END) AS 못죽_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%답답%'    THEN 1 ELSE 0 END) AS 답답_언급,
    SUM(CASE WHEN voted_up=0 AND review_text LIKE '%기절%'    THEN 1 ELSE 0 END) AS 기절_언급,
    SUM(CASE WHEN voted_up=0 THEN 1 ELSE 0 END)                                 AS 부정_리뷰_전체수
FROM reviews;

-- ----------------------------------------------------------------------
-- 3단계: 결과 출력
-- ----------------------------------------------------------------------
SELECT '=== [1] 리뷰 전체 요약 ===' AS section;
SELECT * FROM review_summary;

-- [스코프 조정] "PC" 키워드는 최종 분석에서 제외함 — "PC를 재부팅"처럼 하드웨어
-- (컴퓨터)를 가리키는 용례가 확인됐고, 나머지 사례도 자동 매칭만으로는 의미를
-- 단정하기 어려운 다의어였음. 신뢰도 낮은 키워드라 "설계·UX 불만"으로 범위를
-- 좁힘(못죽/답답/기절 3개 키워드로 대체 확인)
SELECT '=== [2] 부정 리뷰 내 키워드별 언급 건수 및 비율 ===' AS section;
SELECT
    '레비아탄' AS 키워드, 레비아탄_언급 AS 언급건수,
    ROUND(100.0 * 레비아탄_언급 / 부정_리뷰_전체수, 1) AS 비율_퍼센트
FROM keyword_frequency
UNION ALL
SELECT '튕김(어근:튕)', 튕김_언급, ROUND(100.0 * 튕김_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
UNION ALL
SELECT '크래시', 크래시_언급, ROUND(100.0 * 크래시_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
UNION ALL
SELECT '어그로', 어그로_언급, ROUND(100.0 * 어그로_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
UNION ALL
SELECT '최적화', 최적화_언급, ROUND(100.0 * 최적화_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
UNION ALL
SELECT '단조(어근)', 단조_언급, ROUND(100.0 * 단조_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
UNION ALL
SELECT '지루(어근)', 지루_언급, ROUND(100.0 * 지루_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
UNION ALL
SELECT '생태계', 생태계_언급, ROUND(100.0 * 생태계_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
UNION ALL
SELECT '못죽(어근)', 못죽_언급, ROUND(100.0 * 못죽_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
UNION ALL
SELECT '답답(어근)', 답답_언급, ROUND(100.0 * 답답_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
UNION ALL
SELECT '기절', 기절_언급, ROUND(100.0 * 기절_언급 / 부정_리뷰_전체수, 1) FROM keyword_frequency
ORDER BY 언급건수 DESC;
