from graphviz import Digraph

dot = Digraph(comment="LedgerMate Architecture", format="png")
dot.attr(rankdir="LR", size="8,5")

# Users
dot.node("User", "사용자\n(회계 담당자 등)", shape="box", style="filled", fillcolor="lightblue")

# Upload
dot.node("Budget", "예산안 업로드\n(HWPX/DOCX)", shape="folder", fillcolor="lightyellow", style="filled")
dot.node("Policy", "규정 업로드\n(PDF/HWP)", shape="folder", fillcolor="lightyellow", style="filled")
dot.node("Receipt", "영수증 업로드\n(Image/PDF)", shape="folder", fillcolor="lightyellow", style="filled")

# Upstage Services
dot.node("UDP", "Upstage Document Parser\n(조항/목차/테이블)", shape="component", fillcolor="white")
dot.node("OCR", "Upstage OCR API\n(한글 영수증 인식)", shape="component", fillcolor="white")

# Processing
dot.node("Match", "매칭 앙상블\n(Rule + RAG-lite + LLM)", shape="box3d", fillcolor="white")
dot.node("Validation", "규정 검증/초과 여부", shape="box3d", fillcolor="white")

# Databases
dot.node("PG", "PostgreSQL + pgvector\n(규정 임베딩)", shape="cylinder", fillcolor="lightgrey", style="filled")
dot.node("S3", "AWS S3\n(원본 파일 저장)", shape="cylinder", fillcolor="lightgrey", style="filled")
dot.node("Mongo", "MongoDB\n(OCR 원문/좌표)", shape="cylinder", fillcolor="lightgrey", style="filled")
dot.node("Snow", "Snowflake\n(로그/분석/ML)", shape="cylinder", fillcolor="lightgrey", style="filled")

# Output
dot.node("Report", "결산안 리포트\n(HWPX/DOCX)", shape="note", fillcolor="lightgreen", style="filled")
dot.node("Dashboard", "대시보드\n(정확도/지출분석)", shape="note", fillcolor="lightgreen", style="filled")

# Connections
dot.edges([("User","Budget"), ("User","Policy"), ("User","Receipt")])
dot.edges([("Budget","UDP"), ("Policy","UDP")])
dot.edge("Receipt","OCR")

dot.edge("UDP","PG")
dot.edge("UDP","S3")
dot.edge("OCR","Mongo")
dot.edge("OCR","Snow")
dot.edge("OCR","Match")
dot.edge("PG","Match")
dot.edge("Snow","Match")
dot.edge("Match","Validation")
dot.edge("Validation","Snow")
dot.edge("Validation","Report")
dot.edge("Report","User")
dot.edge("Dashboard","User")

# Save and render
file_path = "/Users/gim-yeseul/Documents/LedgerMate/img_diagram"
dot.render(file_path)
file_path +".png"
