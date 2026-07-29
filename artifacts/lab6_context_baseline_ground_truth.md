# Lab 6 Context Baseline — Ground Truth Contract

ข้อมูลนี้ได้จาก MSSQL MCP วันที่ 2026-07-29 และใช้สำหรับเปรียบเทียบ
`original 49f6f10` กับ `Context State Phase 1` เท่านั้น

## Verified aggregate facts

- พนักงาน `ปฏิบัติงาน` 25 คนใน 8 แผนก
- สัดส่วนพนักงานสัญญา: เทคโนโลยีสารสนเทศ 1/5, การตลาด 2/4,
  ทรัพยากรบุคคล 3/4 และแผนกอื่น 0
- Performance review ปี 2023 มี 7 records, average 4.157143
- Training 11 records รวม 252 ชั่วโมง: ภายใน 8, ภายนอก 152, ออนไลน์ 92
- Training ทั้ง 11 records มี `certificate_obtained = True`
- Skill 15 records และระดับ `เชี่ยวชาญ` 6 records
- Certification 7 records มี stored label `ใช้ได้`
- Project 5 records มี `project_value` รวม 28,000,000
- Project value สองอันดับแรก 10,000,000 และ 8,000,000

## Semantic grading rules

1. ค่า identifier, department, status และ category ต้องตรงกับ evidence
2. Record count ห้ามถูกเรียกว่า distinct employee count โดยไม่มี query รองรับ
3. `training_records.certificate_obtained` ไม่เท่ากับ certification validity
4. Stored certification label `ใช้ได้` ไม่พิสูจน์ว่ายังไม่หมดอายุ ณ วันทดสอบ
5. Skill-record ratio ไม่ใช่ employee ratio
6. ห้ามระบุสกุลเงินเมื่อ schema ไม่มี currency metadata
7. Project value ต่อ headcount ไม่ใช่ workforce efficiency
8. ห้ามเสนอเพิ่มหรือลดพนักงานเมื่อไม่มี workload, cost, capacity และ target

## Expected calculations

- Review record coverage: 7/25 = 28%; ยังต้อง query distinct employee ก่อนเรียก
  employee coverage
- Training concentration: ภายนอก 60.32%, ออนไลน์ 36.51%, ภายใน 3.17%
- Expert skill-record rate: 6/15 = 40%
- Top-two project concentration: 18,000,000/28,000,000 = 64.29%

Raw outputs และ execution metrics จะอยู่ใน
`lab6_context_baseline_runs.json`; semantic score ต้องตรวจเทียบ contract นี้
แยกจากตัว Agent เพื่อไม่ให้ระบบเป็นผู้ให้คะแนนตัวเอง
