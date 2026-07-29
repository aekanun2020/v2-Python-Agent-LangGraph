# Lab 6 Original vs Context State Phase 1

วันที่ทดสอบ: 2026-07-29  
Model: `qwen/qwen3.5-35b-a3b` ผ่าน OpenRouter  
MCP: `https://7ff8-184-22-21-43.ngrok-free.app/mcp`  
จำนวน: 10 คำถาม × 2 variants = 20 live runs

Variants:

- `original_49f6f10`
- `context_state_phase1` จาก commit `62929c7`

คำถามและ ground truth อยู่ใน `lab6_context_baseline_ground_truth.md` ส่วน raw
stdout, answer, latency และ tool-call count อยู่ใน
`lab6_context_baseline_runs.json`

## Execution results

| Metric | Original | Context State Phase 1 |
|---|---:|---:|
| Process สำเร็จ | 10/10 | 10/10 |
| มีคำตอบที่ไม่ใช่ `None` | 8/10 | 9/10 |
| Timeout | 0 | 0 |
| Mean latency | 22.56 s | 25.19 s |
| Median latency | 16.38 s | 25.03 s |
| MCP tool calls รวม | 68 | 83 |
| Context alerts | ไม่มี | 0 |

Phase 1 ช้ากว่าเฉลี่ยประมาณ 11.7% และเรียก MCP มากกว่าประมาณ 22.1% ใน sample
นี้ แต่เป็นการรันเพียงหนึ่งครั้งต่อคำถาม จึงยังแยก model variance ออกจากผลของ
scaffolding ไม่ได้

## Manual semantic grading

ใช้ ground-truth contract ตรวจสองระดับ:

1. **Core result**: ตัวเลขหรือ business-rule result หลักถูก
2. **Strict grounded answer**: ทุก claim ต้องมี evidence, ใช้ grain ถูก,
   ไม่สร้าง currency, causation หรือ recommendation เกินข้อมูล

| Question | Original core | Phase 1 core | ปัญหาสำคัญ |
|---|---|---|---|
| Q1 headcount | ผ่าน | ไม่ตอบ | Original แนะนำปรับคน/automation เกินหลักฐาน |
| Q2 employment mix | ผ่าน | ผ่าน | ทั้งคู่อนุมานเหตุผลการใช้พนักงานสัญญาและเสนอ HR action |
| Q3 contract policy | ผ่านแบบมี contradiction | ผ่าน | ทั้งคู่เปลี่ยน policy flag เป็นข้อเสนอเปลี่ยนพนักงาน |
| Q4 review coverage | ผ่านเฉพาะ 7/25 | ผ่านเฉพาะ 7/25 | เรียก 7 records ว่า 7 employees โดยไม่พิสูจน์ distinct |
| Q5 training portfolio | ผ่าน | ผ่าน | อนุมาน cost/risk และเสนอปรับ training mix โดยไม่มีข้อมูลต้นทุน |
| Q6 certificate semantics | ไม่ตอบ | ไม่ผ่าน | Phase 1 สร้างตัวเลข 20 valid, 5 expired, 6 missing ที่ขัดกับ evidence 7 records |
| Q7 expert skills | ไม่ผ่าน | ผ่าน | Original นับ expert เป็น 0; Phase 1 ใช้ record ratio เป็น people capability |
| Q8 project concentration | ผ่าน | ผ่าน | ทั้งคู่เติมหน่วย `บาท` ทั้งที่ schema ไม่มี currency metadata |
| Q9 efficiency trap | ไม่ตอบ | ไม่ผ่าน | Phase 1 เรียก project value/head ว่า efficiency และเติม `บาท` |
| Q10 staffing decision | ไม่ผ่าน | ไม่ผ่าน | ทั้งคู่เสนอเพิ่ม/ลดคนจากข้อมูลที่ไม่พอ |

สรุปคะแนน:

| Score | Original | Context State Phase 1 |
|---|---:|---:|
| Core result ถูก | 6/10 | 6/10 |
| Strict grounded answer | 0/10 | 0/10 |

คะแนน strict เป็นศูนย์เมื่อคำตอบมี unsupported claim แม้ตัวเลขหลักถูก เพราะโจทย์นี้
ต้องการตรวจ “ผลสำเร็จแต่ผิดเชิงความหมาย” ไม่ใช่เพียง query สำเร็จ

## Proven conclusion

Phase 1 **ยังไม่ดีกว่า original ในด้านความฉลาดหรือความถูกต้องเชิงความหมาย**:

- deterministic Context State ไม่พบ alert ในทุก run
- แต่คำตอบยัง hallucinate, ใช้ data grain ผิด และให้คำแนะนำเกิน evidence
- Q6 แสดง false-success ชัดที่สุด: process จบ, tool ถูกเรียก, ไม่มี alert แต่คำตอบ
  สร้างจำนวน certification ที่ ground truth ไม่รองรับ
- Q9 และ Q10 แสดงว่า state observer ไม่สามารถแยก metric/proxy ออกจาก business
  decision ได้

Phase 1 มีคุณค่าเฉพาะ observability และ loop/error signatures ตามขอบเขตเดิม
ไม่ควรอ้างว่าช่วย semantic quality

## Next experiment

สร้าง Phase 2 เป็น **Final Semantic Observer** ที่รับ:

- user question และ explicit business rule
- accepted tool evidence
- proposed answer
- ground-truth-neutral policy เช่น grain, unsupported unit, causal claim,
  recommendation evidence และ exact canonical labels

ผลลัพธ์ต้องเป็น structured verdict:

```text
approve | rewrite | query_more | refuse_decision
```

จากนั้นรันคำถามเดิมซ้ำอย่างน้อย 3 seeds ต่อ variant และวัด:

- strict grounded-answer rate
- unsupported-claim rate
- unnecessary MCP re-query rate
- completion, latency, tool calls และ token cost

เงื่อนไขผ่านเบื้องต้น: strict grounded answer ดีขึ้นโดยไม่มี completion regression
และ `rewrite` ต้องไม่ query MCP ใหม่เมื่อ evidence ครบแล้ว
