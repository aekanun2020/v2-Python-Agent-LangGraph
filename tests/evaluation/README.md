# Unseen Paraphrase + Boundary Evaluation

ชุดนี้ freeze ก่อนรัน baseline ครั้งแรก และไม่ควรแก้คำถามหลังเห็นผลเพื่อทำให้
score ดีขึ้น

- `*_unseen_paraphrases.json`: คำถามใหม่ที่ควรเลือก contract ที่ระบุ
- `*_boundaries.json`: คำถามใกล้เคียงที่ต้องไม่เลือก contract
- routing evaluation ไม่เรียก LLM หรือ MCP
- `--live` เรียก MCP เฉพาะ paraphrase ที่ routing ถูก และรันหนึ่งครั้งต่อ
  contract ที่ไม่ซ้ำ

รัน routing baseline:

```bash
python scripts/evaluate_skill_routing.py
```

รัน routing พร้อม live MCP:

```bash
python scripts/evaluate_skill_routing.py --live \
  --output artifacts/unseen_boundary_baseline.json
```

Metrics:

- `contract_recall`: paraphrase ที่เลือก contract ถูก
- `boundary_precision`: boundary ที่ไม่ถูกจับเข้า contract
- `false_match_rate`: boundary ที่ถูกจับผิด
- `live_contract_completion`: live query ที่ evidence ครบตาม contract

ผล baseline ต้องถูกบันทึกก่อนปรับ selector/router

ผล baseline แรกอยู่ที่
[`artifacts/unseen_boundary_baseline_report.md`](../../artifacts/unseen_boundary_baseline_report.md):
paraphrase recall `55%`, boundary precision `95%`, false match `5%`; live MCP
ผ่าน `11/11` contracts สามรอบด้วย normalized evidence hash เดียวกัน
