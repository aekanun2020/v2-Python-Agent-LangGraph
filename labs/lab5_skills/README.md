# Lab 5 — Skill Routing และ Progressive Disclosure

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 2.1

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** Layer 3 (Tools+**Skills**) + Layer 1 (Instructions) — โหลด skill ตาม domain แบบ Progressive Disclosure (เลือก context ที่ป้อนให้โมเดล)

---

## จุดประสงค์การเรียนรู้

- เข้าใจหลัก **Progressive Disclosure** — ใส่เฉพาะ "ดัชนี skill" (ชื่อ+คำอธิบายสั้น) ลง context แทนที่จะยัดเนื้อหาเต็มทุก skill (ประหยัด token และทำให้พฤติกรรม LLM คงเส้น)
- ใช้ `SkillLoader` อ่าน `SKILL.md` จากแต่ละโฟลเดอร์ skill และ route คำถามไปยัง skill ที่ตรงที่สุด
- โหลดเนื้อหาเต็มเฉพาะ skill ที่ถูก route ก่อนทำงานด้วย MCP tools (ต่อยอดจาก Lab 4)

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)
- ต้องมี `MCP_SERVER_URL` ใน `.env` ชี้ไปยัง MCP MSSQL Server จริง

---

## วิธีรัน

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # รันจาก root repo (เพราะ import labs.core.*)

# ตัวอย่างที่ 1: คำถามเกี่ยวกับ HR → route ไป hr_analytics
python labs/lab5_skills/agent_skills.py "แต่ละแผนกมีพนักงานกี่คน"

# ตัวอย่างที่ 2: คำถามเกี่ยวกับลูกค้า → route ไป customer_service
python labs/lab5_skills/agent_skills.py "ลูกค้าโกรธมาก ขอคุยหัวหน้า"
```

---

## อธิบายจุดสำคัญของโค้ด

### `skill_loader.py` — SkillLoader

#### `_scan()` — อ่านดัชนี skill จากโฟลเดอร์

```python
for entry in sorted(os.listdir(self.skills_dir)):
    path = os.path.join(self.skills_dir, entry, "SKILL.md")
    if os.path.isfile(path):
        meta = _parse_front_matter(f.read())   # อ่าน name + description จาก front-matter YAML
        self._skills[name] = {"description": meta["description"], "path": path}
```

`_parse_front_matter()` แกะบล็อก `--- ... ---` ที่หัวไฟล์ SKILL.md เพื่อดึง `name` และ `description`

#### `index_for_prompt()` — Progressive Disclosure

สร้างข้อความ "Skills ที่ใช้ได้: ..." โดยใส่แค่ชื่อ+คำอธิบายสั้น ไม่ยัดเนื้อหาเต็ม ป้องกัน context bloat

#### `load_full(name)` — โหลดเนื้อหาเต็มเฉพาะ skill ที่ถูกเลือก

เปิดอ่าน `SKILL.md` ของ skill นั้นทั้งไฟล์เพียงครั้งเดียวหลัง routing ตัดสินใจแล้ว

#### `route_from_reply(reply)` — แกะ skill ที่ LLM เลือก

```python
m = re.search(r"SKILL:\s*([a-zA-Z_]+)", reply or "")
return m.group(1).strip() if m else None
```

LLM ต้องขึ้นบรรทัดแรกด้วย `"SKILL: <ชื่อ>"` จึงจะ route ได้ถูกต้อง

### `agent_skills.py` — ฟังก์ชัน `run()`

#### (1) Routing round

```python
routing_system = BASE_SYSTEM + "\n\n" + loader.index_for_prompt()
route_resp = llm.chat(messages=[...], max_tokens=30)
chosen = SkillLoader.route_from_reply(route_resp.choices[0].message.content)
```

รอบแรกใช้ `max_tokens=30` — ขอแค่ชื่อ skill ไม่ต้องการคำตอบยาว

#### (2) โหลดและทำงาน

```python
skill_body = loader.load_full(chosen) if chosen else ""
system += "\n\n[เนื้อหา skill ที่ใช้กับงานนี้]\n" + skill_body
```

ใส่เนื้อหา skill ที่เต็มลง system prompt ก่อนรัน agent loop + MCP tools เหมือน Lab 4

> จุดที่ควรเปิดอ่าน: `labs/lab5_skills/skills/hr_analytics/SKILL.md` และ `customer_service/SKILL.md` — ดู front-matter YAML และเนื้อหาที่จะถูกโหลดเข้า context

---

## ผลลัพธ์ที่คาดหวัง

```
[skills] พบ 3 skills: ['customer_service', 'database_query', 'hr_analytics']
[MCP] ค้นพบ 5 tools

[user] แต่ละแผนกมีพนักงานกี่คน
[route] เลือก skill: hr_analytics
[step 1] เรียก 1 tool
------------------------------------------------------------
[answer]
แผนก IT มีพนักงาน 5 คน, แผนก HR มี 3 คน, ...
```

ดู screenshot ตัวอย่าง: `../../screenshots/labs/lab5_skill_routing.png`
