# v2-Python-Agent-LangGraph


## ผลไหนโดดเด่นที่สุด


**V2 เด่นที่สุดด้านผลลัพธ์ที่ทำซ้ำได้ใน bounded domain**: ชุด HR ผ่าน 10/10 คำถามและ 77/77 atomic items สองรอบ ส่วน Finance ผ่าน 10/10 คำถามและ 148/148 atomic items สองรอบ โดย HR ให้ answer hash เดียวกันและ Finance ไม่ regression หลังเพิ่ม HR Skill ผลนี้ชี้ว่า deterministic Skill contract ให้คำตอบเร็วและคงที่เมื่อคำถามอยู่ในขอบเขตที่ประกาศไว้ แต่ไม่ใช่หลักฐานว่าครอบคลุม paraphrase หรือคำถามนอก contract ทั้งหมด.







### Repositories ในสายเดียวกัน

- [Original — Python-Agent-LangGraph](https://github.com/aekanun2020/Python-Agent-LangGraph)
- [V2 — v2-Python-Agent-LangGraph](https://github.com/aekanun2020/v2-Python-Agent-LangGraph)
- [V3 — v3-Python-Agent-LangGraph](https://github.com/aekanun2020/v3-Python-Agent-LangGraph)
- [V4 — v4-Python-Agent-LangGraph-](https://github.com/aekanun2020/v4-Python-Agent-LangGraph-)
- [V5 — v5-Python-Agent-LangGraph](https://github.com/aekanun2020/v5-Python-Agent-LangGraph)
- [V6 — v6-Python-Agent-LangGraph](https://github.com/aekanun2020/v6-Python-Agent-LangGraph)
- [V7 — v7-Python-Agent-LangGraph](https://github.com/aekanun2020/v7-Python-Agent-LangGraph)

## สถานะปัจจุบัน: Pure Python Agent + bounded-domain Skills




งานพัฒนาล่าสุดอยู่ที่ **Lab 6** และไม่ใช้ LangGraph ใน critical path:




```text
Skill contract -> MCP evidence -> deterministic checks
               -> LLM semantic review เฉพาะกรณีเสี่ยง
               -> fail-closed Claim Gate -> Answer
```




แนวคิดสำคัญคือ Observation เพียงอย่างเดียวไม่รู้ความหมายทางธุรกิจ:




- **Skill** เก็บ semantics และ policy ของ bounded domain
- **Contract** นิยาม query, grain, field, label และ completion rule ที่ runtime ตรวจได้
- **Observation** ตรวจผล tool เทียบกับ state และ contract
- **Claim Gate** ปล่อยเฉพาะ claim ที่ accepted evidence รองรับ




Runtime core ค้นหา contracts จาก
`skills/*/references/answer_contracts.json`; ไฟล์ generic
`labs/lab6_todo/executable_metric_contracts.json` ไม่มี HR/Finance contract
เพื่อไม่ให้ core ผูกกับโดเมนใดโดเมนหนึ่ง




Skills ปัจจุบัน:




- [HR Analytics](skills/hr-analytics/SKILL.md)
- [Finance Analytics](skills/finance-analytics/SKILL.md)
