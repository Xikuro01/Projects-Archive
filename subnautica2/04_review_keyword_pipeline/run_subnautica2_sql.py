"""
subnautica2_review_analysis.sql을 실행하고 결과를 출력하는 러너.
[역할 구분] 실행 및 출력만 담당 — 분석 로직은 전부 .sql 파일 안에 있음.
"""
import sqlite3

conn = sqlite3.connect("/home/claude/subnautica2_reviews.db")
cur = conn.cursor()

with open("/home/claude/subnautica2_review_analysis.sql", "r") as f:
    sql_script = f.read()

cur.executescript(sql_script)
conn.commit()

queries = [
    ("[1] 리뷰 전체 요약", "SELECT * FROM review_summary"),
    ("[2] 부정 리뷰 내 키워드별 언급 건수 및 비율", """
        SELECT '레비아탄' AS 키워드, 레비아탄_언급 AS 언급건수,
               ROUND(100.0*레비아탄_언급/부정_리뷰_전체수,1) AS 비율_퍼센트
        FROM keyword_frequency
        UNION ALL
        SELECT '튕김(어근:튕)', 튕김_언급, ROUND(100.0*튕김_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        UNION ALL
        SELECT '크래시', 크래시_언급, ROUND(100.0*크래시_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        UNION ALL
        SELECT '어그로', 어그로_언급, ROUND(100.0*어그로_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        UNION ALL
        SELECT '최적화', 최적화_언급, ROUND(100.0*최적화_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        UNION ALL
        SELECT '단조(어근)', 단조_언급, ROUND(100.0*단조_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        UNION ALL
        SELECT '지루(어근)', 지루_언급, ROUND(100.0*지루_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        UNION ALL
        SELECT '생태계', 생태계_언급, ROUND(100.0*생태계_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        UNION ALL
        SELECT '못죽(어근)', 못죽_언급, ROUND(100.0*못죽_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        UNION ALL
        SELECT '답답(어근)', 답답_언급, ROUND(100.0*답답_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        UNION ALL
        SELECT '기절', 기절_언급, ROUND(100.0*기절_언급/부정_리뷰_전체수,1) FROM keyword_frequency
        ORDER BY 언급건수 DESC
    """),
]

for title, q in queries:
    print("=" * 70)
    print(title)
    print("=" * 70)
    cur.execute(q)
    cols = [d[0] for d in cur.description]
    print(" | ".join(cols))
    for row in cur.fetchall():
        print(row)
    print()

conn.close()
