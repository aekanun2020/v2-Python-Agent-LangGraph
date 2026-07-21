# Lab 6 — TodoWrite: วางแผน Multi-step Task

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 2.2

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** Layer 3 (Skills) + เริ่มแตะ Layer 2 (Memory) — TodoWrite คือ state ของแผนงานหลายขั้นที่ไหลข้าม step

---

## จุดประสงค์การเรียนรู้

- เพิ่ม internal tools (`todo_write`, `todo_update`) เพื่อให้ agent วางแผนงานหลายขั้นก่อนเริ่มลงมือ
- เข้าใจการจัดการ **state ใน agent** ด้วย class `TodoState` ที่เก็บ todo list ไว้ใน memory
- เห็นว่า agent ใช้ todo เป็นแผนงาน แล้วอัปเดตสถานะ (todo → doing → done) ระหว่างทำงานจริงด้วย MCP tools

> `agent_todo.py` คือเวอร์ชันพื้นฐานเพื่อเรียนรู้ TodoWrite: โมเดลเป็นผู้ประกาศสถานะเอง
> จึงยังไม่ใช่ planner runtime ที่ตรวจหลักฐาน ดูหัวข้อ Pure Python Planner ด้านล่าง

## Enhanced: Pure Python Evidence-driven Planner

ไฟล์ `agent_planner.py` เพิ่ม planner จริงโดยไม่ใช้ LangGraph ส่วน Python runtime เป็น
เจ้าของ state transition แทนการเชื่อคำประกาศของ LLM:

- มี `PlannerState`, revision และสถานะของแต่ละขั้น
- Dynamic Observation Policy ตรวจ active step + tool + result type ก่อนรับหลักฐาน
- MCP result ถูกผูกกับ step ที่ `in_progress` เมื่อ observation ตัดสิน `accept`
- `plan_complete` ถูกปฏิเสธทันทีถ้ายังไม่มี tool evidence
- แก้แผนระหว่างทำงานผ่าน `plan_revise` และรักษาหลักฐานเดิม
- final answer ถูก runtime gate ปฏิเสธจนกว่าทุกขั้นเสร็จและมีหลักฐาน

### โหมดล่าสุดที่ควรใช้

Runtime มี Risk Router สามโหมด โดยค่า default ยังคงเป็น `rules` เพื่อไม่เปลี่ยน
behavior เดิม ส่วนโหมดที่แนะนำสำหรับเรียนรู้และเก็บผล reviewer คือ `shadow`:

```bash
OBSERVATION_ROUTING_MODE=shadow make run-pure-planner
```

ใน Shadow mode hard rules ยังเป็นผู้ตัดสิน evidence เหมือนเดิม เฉพาะผล high risk
ที่ผ่าน hard checks แล้วจึงเรียก Qwen reviewer และบันทึกผลลง trace โดย reviewer
ไม่มีสิทธิ์ block หลักฐาน ผล regression ล่าสุดคือ Rules 8/8, Shadow 8/8,
behavior regression 0 และ reviewer calls ลดลง 62.5%

```text
MCP result → hard observation → risk router
                            ├─ low/medium → hard decision
                            └─ high → Qwen review (shadow only)
                                      ↓
                              hard decision remains final
```

ยังไม่แนะนำ `OBSERVATION_ROUTING_MODE=enforce` เป็น default เพราะ captured Qwen run
มี false reject corrected join หนึ่งครั้ง ดูภาพสรุปล่าสุดที่
`../../artifacts/lab6_hr_shadow_router_comparison.png`

```text
while (plain Python):
  LLM proposes action
  → Python validates transition
  → MCP executes
  → Dynamic observation: accept / retry / query_more / reject
  → Python binds accepted evidence to active step
  → incomplete/unsupported answer is rejected
```

พิสูจน์กติกาโดยไม่ใช้ LLM/MCP และรัน Agent จริงตามลำดับ:

```bash
make proof-pure-planner
make run-pure-planner
make compare-lab6-hr
make compare-observation-policy-hr
make compare-semantic-observation-hr
make compare-semantic-matrix-hr
make compare-prompt-observation-hr
make compare-shadow-router-hr
```

ความแตกต่างสำคัญ: LLM ยังใช้ reasoning เพื่อสร้าง/แก้แผน แต่ไม่มีสิทธิ์เปลี่ยน
ขั้นเป็น `completed` หรืออนุมัติคำตอบเองหาก runtime ยังไม่พบหลักฐาน

### เปรียบเทียบของเดิมกับของใหม่บนโจทย์ HR

```bash
make validate-hr-challenges
make compare-lab6-hr HR_CHALLENGE=skills_project_risk
make compare-lab6-hr-adversarial HR_CHALLENGE=skills_project_risk
```

คำสั่งนี้รัน `agent_todo.py` และ `agent_planner.py` แบบเรียงลำดับด้วยคำถาม,
model และ MCP เดียวกัน แล้วบันทึกผล JSON/HTML ใน `artifacts/` การเทียบนี้แยกจาก
Lab 8 โดยสมบูรณ์และไม่มี LangGraph อยู่ใน execution path

`skills_project_risk` ใช้ analytical contract เดียวกันทั้งสองฝั่ง: aggregation
หนึ่งแถวต่อพนักงาน, flags `f1–f5` และ tier thresholds ตายตัว ส่วน adversarial mode
จำลอง late grain audit หนึ่งครั้งเพื่อพิสูจน์ runtime rejection → revision → retry

ผล Qwen ปกติของ `skills_project_risk`: TodoWrite ใช้ MCP 7 calls / 77.564 วินาที;
Pure Python Planner ใช้ 11 calls / 97.163 วินาที, completed 9/9 และ Answer Gate
= APPROVED ดูภาพได้ที่ `../../artifacts/lab6_hr_comparison_skills_project_risk.png`

ผล Qwen adversarial: Pure Planner ถูกปฏิเสธ query ก่อนส่ง MCP, ฟื้นตัวจน revision 6,
completed 2/2 และ APPROVED โดยใช้ 16 MCP calls / 752.206 วินาที

### Controlled proof: Dynamic Observation Policy

Planner รุ่นแรกห้าม evidence ว่าง แต่ยังรับข้อความ error ที่ไม่ว่างได้
`observation_policy.py` จึงเพิ่ม hard policy ที่เปลี่ยนตาม step, tool capability และ
result type ก่อนเรียก `PlannerState.observe()`

```bash
make compare-observation-policy-hr
```

คำสั่งนี้ไม่ใช้ LLM key เพื่อ isolate จังหวะ Observation โดยเรียก SQL read-only กับ
HR MCP จริง 2 ครั้ง: รอบแรกจำลอง 502 หลัง MCP ตอบ แล้ว retry action เดิม ผลที่บันทึกได้คือ
PlannerState เดิมรับ invalid evidence 1 ครั้ง ส่วน Dynamic Policy รับ 0, ตัดสิน `retry`
แล้วรับ successful result เป็น evidence ดู captured screen ที่
`../../artifacts/lab6_hr_dynamic_observation_policy.png` และ trace เต็มในไฟล์ JSON ข้างกัน

ขอบเขตของหลักฐาน: พิสูจน์ evidence admission และ recovery path ไม่ได้พิสูจน์คุณภาพ
คำตอบ HR หรือความฉลาดโดยรวมของ agent

`make compare-semantic-observation-hr` ทดสอบกรณีที่ทั้ง query ผิดและ query แก้
execute สำเร็จจริง โดย step ต้องการ active employees แยกแผนก แต่ query แรกนับทั้งตาราง
Structural checks ยอมรับ query ผิด ส่วน Semantic Policy ตรวจพบ missing population filter
และ department grain, ปฏิเสธ evidence แล้วรับ corrected retry ดูภาพที่
`../../artifacts/lab6_hr_semantic_observation.png`

`make compare-semantic-matrix-hr` ขยายเป็น 4 adversarial contracts: denominator,
pre-review/latest-review temporal window, multi-satellite join cardinality และ
cross-evidence contradiction ผล captured run ผ่าน 4/4 ด้วย 9 live MCP calls;
wrong queries ทุกตัว execute สำเร็จและ structural checks รับ แต่ semantic policy
ตัดสิน `retry` ทั้งหมด ก่อนรับ corrected queries เป็น `accept` ดูภาพที่
`../../artifacts/lab6_hr_semantic_matrix.png`

### Optional Qwen Semantic Reviewer + Hybrid gate

เปิด prompt reviewer ใน agent จริงด้วย:

```bash
OBSERVATION_ROUTING_MODE=rules make run-pure-planner   # default
OBSERVATION_ROUTING_MODE=shadow make run-pure-planner # reviewer advisory
OBSERVATION_ROUTING_MODE=enforce make run-pure-planner
```

reviewer ใช้ system prompt แยก context เพื่อ derive semantic requirements แล้วคืน JSON
ส่วน Hybrid ให้ hard failure veto เสมอและเรียก reviewer เฉพาะ hard checks ที่ผ่าน
ผล comparison Qwen: rules 8/8, prompt 7/8 admission accuracy และ Hybrid 7/8;
prompt มี false reject corrected join หนึ่งครั้ง ใช้ 52.434 วินาทีและ 12,507 tokens
หาก route แบบ Hybrid จะลด reviewer calls จาก 8 เหลือ 4 ดูภาพที่
`../../artifacts/lab6_hr_prompt_reviewer_comparison.png`

Shadow Router จัด observation เป็น low/medium/high และเรียก Qwen เฉพาะ high risk ที่
hard checks ผ่าน ใน `shadow` reviewer decision ถูกบันทึกใน trace แต่เปลี่ยน evidence
ไม่ได้ ผล replay: high-risk recall 6/6, reviewer calls ลด 62.5%, disagreement 1 และ
behavior regression = 0 ดูภาพ `../../artifacts/lab6_hr_shadow_router_comparison.png`

`PROMPT_SEMANTIC_REVIEW=1` ยังรองรับย้อนหลังและเทียบเท่า `enforce` แต่ผู้เรียนควรใช้
`OBSERVATION_ROUTING_MODE` เพราะแสดงอำนาจของ reviewer ชัดกว่า

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)
- ต้องมี `MCP_SERVER_URL` ใน `.env` ชี้ไปยัง MCP MSSQL Server จริง

---

## วิธีรัน

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # รันจาก root repo (เพราะ import labs.core.*)

python labs/lab6_todo/agent_todo.py
```

(default task คือรายงาน HR 3 ขั้น: นับพนักงานแยกแผนก → top-3 มูลค่าโครงการ → สรุปเชิงธุรกิจ)

---

## อธิบายจุดสำคัญของโค้ด

ไฟล์: `labs/lab6_todo/agent_todo.py`

### `TodoState` — state ของ todo list (in-memory)

```python
class TodoState:
    def write(self, items: list[str]) -> str: ...    # สร้าง todo ใหม่ทั้งหมด
    def update(self, index: int, status: str) -> str: ...  # เปลี่ยนสถานะทีละข้อ
    def render(self) -> str: ...                     # แสดง [ ] / [~] / [x] ต่อ item
```

`render()` คืน string เช่น `"[x] 1. นับพนักงาน\n[~] 2. top-3\n[ ] 3. สรุป"` — LLM อ่านและรู้สถานะปัจจุบันของแผนงาน

> จุดที่ควรเปิดอ่าน: method `update()` — มี logic รองรับทั้ง 1-based index (ตาม render) และ 0-based (ที่ LLM บางครั้งส่งมาผิด) เพื่อความทนทาน

### `build_tools(registry)` — รวม todo tools + MCP tools

```python
todo_tools = [
    {tool: "todo_write", ...},   # สร้าง todo list
    {tool: "todo_update", ...},  # อัปเดตสถานะ
]
return todo_tools + registry.openai_tools   # รวมกับ MCP tools
```

agent เห็น tools ทั้งหมดรวมกัน — ตัดสินใจว่าจะใช้ todo tool หรือ MCP tool ตามความเหมาะสม

### `run(question, registry, max_steps=30)` — agent loop + todo dispatch

```python
if name == "todo_write":
    result = todo.write(args.get("items", []))
elif name == "todo_update":
    result = todo.update(args.get("index"), args.get("status"))
else:
    result = registry.dispatch(name, args)   # MCP tool
```

todo tools ถูก handle ใน Python โดยตรง (ไม่ผ่าน MCP) ส่วน tools อื่นส่งไป `registry.dispatch()`

### System prompt — บังคับ planning ก่อน action

```python
SYSTEM = (
    "...ถ้างานมี 3 ขั้นขึ้นไป ให้เรียก todo_write เขียนแผนก่อนเริ่มลงมือ "
    "แล้วทำทีละข้อ เรียก todo_update เปลี่ยนสถานะเป็น 'doing' ก่อนทำ และ 'done' เมื่อเสร็จ..."
)
```

pattern นี้คือ **plan-then-execute** ที่ให้ agent โปร่งใสและตรวจสอบได้

---

## ผลลัพธ์ที่คาดหวัง

```
[MCP] ค้นพบ 5 tools

[user] ช่วยทำรายงาน HR: 1) นับพนักงาน... 2) หาพนักงาน... 3) สรุป...
[step 1] TODO_WRITE
[ ] 1. นับพนักงานที่ปฏิบัติงานแยกตามแผนก
[ ] 2. หาพนักงานที่มีมูลค่าโครงการรวมสูงสุด 3 อันดับแรก
[ ] 3. สรุปข้อค้นพบเชิงธุรกิจ
[step 2] TODO_UPDATE -> {'index': 1, 'status': 'doing'}
...
[step N] TODO_UPDATE -> {'index': 3, 'status': 'done'}
------------------------------------------------------------
[answer]
สรุปข้อค้นพบ: แผนก IT มีพนักงานมากที่สุด...
------------------------------------------------------------
[todo สุดท้าย]
[x] 1. นับพนักงานที่ปฏิบัติงานแยกตามแผนก
[x] 2. หาพนักงานที่มีมูลค่าโครงการรวมสูงสุด 3 อันดับแรก
[x] 3. สรุปข้อค้นพบเชิงธุรกิจ
```

ดู screenshot ตัวอย่าง: `../../screenshots/labs/lab6_todowrite.png`
