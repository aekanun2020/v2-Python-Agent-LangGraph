# Lab 6 Phase 1 vs Phase 2 Semantic Observer

วันที่ทดสอบ: 2026-07-29  
Model: `qwen/qwen3.5-35b-a3b` ผ่าน OpenRouter  
MCP: `https://7ff8-184-22-21-43.ngrok-free.app/mcp`  
จำนวน: 10 คำถาม × 2 modes = 20 live runs

Modes ใช้ codebase เดียวกันและ hard MCP budget เดียวกัน:

- `phase1_observer_off`: ปิด Final Semantic Observer
- `phase2_observer_on`: เปิด EvidenceState + Final Semantic Observer + recheck

Raw stdout, stderr, answers, verdicts และ execution metrics อยู่ใน
`lab6_semantic_phase2_runs.json`

## Execution metrics

| Metric | Observer off | Phase 2 on |
|---|---:|---:|
| Process สำเร็จ | 10/10 | 9/10 |
| มีคำตอบที่ไม่ใช่ `None` | 9/10 | 9/10 |
| Timeout | 0 | 0 |
| Mean latency | 25.56 s | 37.42 s |
| Median latency | 22.83 s | 31.31 s |
| MCP calls รวม | 63 | 65 |
| MCP calls ที่ hard budget block | 8 | 1 |
| Semantic LLM verdict calls | 0 | 17 |

Phase 2 ช้ากว่าเฉลี่ยประมาณ 46.4% เพราะคำตอบที่ถูก rewrite/refuse ถูก reviewer
ตรวจซ้ำก่อนแสดงผล ส่วน MCP calls ใกล้เคียงกัน

Process failure หนึ่งครั้งใน Q3 เกิดจาก MCP endpoint ตอบ HTTP 503 และ runtime
ยังไม่มี transient retry จึงนับเป็น completion regression ที่ต้องแก้ ไม่ตัดออกจากผล

## Manual grading against the ground-truth contract

เกณฑ์:

- **Core correct**: ตัวเลข/business-rule result หลักถูก หรือปฏิเสธ decision trap ถูก
- **Strict grounded**: ทุก claim ถูก grain, ไม่มีหน่วย/คำแนะนำ/severity/PII เกินหลักฐาน

| Q | Observer off | Phase 2 | Phase 2 finding |
|---|---|---|---|
| 1 Headcount | core ผ่าน, strict ไม่ผ่าน | strict ผ่าน | rewrite ตัดคำแนะนำ staffing ออก |
| 2 Employment mix | ไม่ผ่าน | strict ผ่าน | แก้จำนวน contract และตัด interpretation |
| 3 Contract policy | ไม่ผ่าน | process fail | MCP HTTP 503 |
| 4 Review coverage | ไม่ตอบ | core ผ่าน, strict ไม่ผ่าน | ยังไม่เตือนว่า 7 records อาจไม่ใช่ 7 distinct employees |
| 5 Training portfolio | core ผ่าน, strict ไม่ผ่าน | strict ผ่าน | ตัด cost/risk recommendation |
| 6 Certificate semantics | core ผ่าน, strict ไม่ผ่าน | core ผ่าน, strict ไม่ผ่าน | ไม่สร้าง 20/5/6 แบบเดิม แต่ยังแสดง employee IDs ที่ไม่จำเป็น |
| 7 Expert skill | core ผ่าน, strict ไม่ผ่าน | core ผ่าน, strict ไม่ผ่าน | Observer ยังปล่อย record ratio ให้กลายเป็น people capability/recommendation |
| 8 Project concentration | core ผ่าน, strict ไม่ผ่าน | core ผ่าน, strict ไม่ผ่าน | ตัด currency แล้ว แต่เพิ่ม severity `High Risk` เกิน policy |
| 9 Efficiency trap | ไม่ผ่าน | strict ผ่าน | refuse decision; ไม่ใช้ project value/head เป็น efficiency |
| 10 Staffing decision | ไม่ผ่าน | core decision ผ่าน, strict ไม่ผ่าน | refuse เพิ่ม/ลดคน แต่ descriptive section มี certification claim ที่ไม่ครบ |

สรุปแบบ conservative:

| Score | Observer off | Phase 2 |
|---|---:|---:|
| Core result/decision correct | 4/10 | 9/10 |
| Strict grounded answer | 0/10 | 4/10 |
| Decision restraint ใน Q9–Q10 | 0/2 | 2/2 |

## What is proven

Phase 2 แก้ failure class สำคัญได้จริง:

- Q1/Q2/Q5: rewrite ตัด unsupported narrative โดยไม่ query MCP ใหม่
- Q9: เปลี่ยน false efficiency conclusion เป็น `refuse_decision`
- Q10: ไม่ยอมเลือกแผนกเพิ่ม/ลดคนจาก descriptive data
- Q6: ไม่เกิด hallucinated certification counts แบบ baseline รอบก่อน
- hard budget จำกัด MCP สูงสุด 12 calls ต่อ task

แต่ยังไม่ควร merge เป็น production behavior:

- strict grounded rate ยังเพียง 4/10
- reviewer model พลาด data grain ใน Q4/Q7
- reviewer เพิ่ม qualitative severity ใน Q8
- rewritten answer ใน Q10 ยังมี unsupported descriptive claim
- semantic recheck เพิ่ม latency สูง
- transient MCP error ยังทำให้ process จบด้วย exception

## Design conclusion

การแยก `ControlState + EvidenceState + ObservationState` ถูกทิศทางและดีกว่าเพิ่ม
ContextAssembler/summary ในตอนนี้ แต่ LLM reviewer อย่างเดียวไม่พอ

ขั้นถัดไปควรเพิ่ม **Evidence Claim Ledger** ก่อน Final Observer:

```text
claim
├─ subject
├─ predicate
├─ value
├─ unit
├─ grain
├─ evidence_ids
└─ derivation
```

แล้วใช้ Python ตรวจ structural invariants (numeric support, unit presence, grain,
canonical labels, evidence references) ส่วน LLM รับผิดชอบเฉพาะ dynamic business
semantics จากนั้นเพิ่ม transient retry และทดสอบอย่างน้อย 3 runs ต่อคำถาม
ก่อนพิจารณา merge
