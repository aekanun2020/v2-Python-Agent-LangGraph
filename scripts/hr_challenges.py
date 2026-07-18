"""Schema-grounded HR questions inspired by People Analytics community practice."""

HR_CHALLENGES = {
    "training_effectiveness": {
        "title": "Training intensity vs latest performance",
        "question": (
            "สำหรับพนักงานที่ยังปฏิบัติงานและมี performance review ให้ใช้ review ล่าสุดต่อคน "
            "รวม training hours ที่จบก่อนหรือในวัน review ให้เหลือหนึ่งแถวต่อพนักงาน แล้ววิเคราะห์ "
            "ความสัมพันธ์ระหว่าง training hours กับ overall_score ทั้งภาพรวมและรายแผนก: แสดง n, "
            "ค่าเฉลี่ย, ช่วงต่ำสุด-สูงสุด และคำนวณ Pearson correlation เมื่อ n และความแปรปรวนเพียงพอ "
            "พร้อมรายงาน coverage ว่าพนักงานกี่คนไม่มี review หรือไม่มี training ที่เชื่อมได้ "
            "ระวัง fan-out จากการ join, เตือน sample size ต่ำ และห้ามสรุปว่า training เป็นสาเหตุของคะแนน"
        ),
        "community_basis": (
            "People Analytics practitioners discuss connecting interventions such as training "
            "to actual outcomes and analyzing learning behavior with performance reviews."
        ),
        "sources": [
            "https://www.reddit.com/r/analytics/comments/1r40o7l/what_does_people_analytics_work_actually_look/",
            "https://www.reddit.com/r/analytics/comments/umbh3n/what_is_people_analytics_and_what_are_the_pros/",
            "https://www.reddit.com/r/humanresources/comments/qxk9ut/transitioning_into_hr_analytics_questions/",
        ],
        "required_fields": [
            "employees.employee_id", "employees.department", "employees.status",
            "performance_reviews.employee_id", "performance_reviews.overall_score",
            "performance_reviews.review_date", "training_records.employee_id",
            "training_records.end_date", "training_records.hours",
        ],
        "preflight_sql": """
WITH latest_review AS (
  SELECT employee_id, overall_score, review_date,
         ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY review_date DESC, review_id DESC) AS rn
  FROM performance_reviews
), training_before_review AS (
  SELECT lr.employee_id, lr.overall_score, lr.review_date,
         COALESCE(SUM(CASE WHEN tr.end_date <= lr.review_date THEN tr.hours ELSE 0 END), 0) AS hours_before,
         MAX(CASE WHEN tr.end_date <= lr.review_date THEN 1 ELSE 0 END) AS trained_before
  FROM latest_review lr
  LEFT JOIN training_records tr ON tr.employee_id = lr.employee_id
  WHERE lr.rn = 1
  GROUP BY lr.employee_id, lr.overall_score, lr.review_date
)
SELECT COUNT(*) AS reviewed_employees,
       COUNT(DISTINCT hours_before) AS distinct_training_hours,
       MIN(hours_before) AS min_training_hours, MAX(hours_before) AS max_training_hours,
       MIN(overall_score) AS min_score, MAX(overall_score) AS max_score
FROM training_before_review
""".strip(),
    },
    "mobility_outcomes": {
        "title": "Internal mobility vs performance and project outcomes",
        "question": (
            "วิเคราะห์พนักงานที่ยังปฏิบัติงานโดยแบ่งเป็น mobility กับ non-mobility: "
            "นิยาม mobility ว่ามี position_history มากกว่า 1 ตำแหน่งหรือเคยอยู่มากกว่า 1 แผนก "
            "เปรียบเทียบ headcount, คะแนน performance review ล่าสุดเฉลี่ย, training hours รวมเฉลี่ยต่อคน "
            "และ project_value รวมเฉลี่ยต่อคน ต้อง aggregate แต่ละตารางให้เหลือหนึ่งแถวต่อพนักงานก่อน join "
            "เพื่อป้องกัน fan-out จากนั้นแจกแจงตามแผนกปัจจุบันและสรุปว่าหลักฐานสนับสนุนหรือไม่ว่า mobility "
            "สัมพันธ์กับผลลัพธ์ที่ดีกว่า โดยห้ามสรุปเป็นเหตุและผล"
        ),
        "community_basis": (
            "Practitioners cite internal movement, promotion statistics, performance reviews, "
            "and linking workforce interventions to outcomes as real People Analytics work."
        ),
        "sources": [
            "https://www.reddit.com/r/analytics/comments/umbh3n/what_is_people_analytics_and_what_are_the_pros/",
            "https://www.reddit.com/r/analytics/comments/1b1axuh/hr_analysts_what_do_you_analyze/",
            "https://www.reddit.com/r/analytics/comments/1r40o7l/what_does_people_analytics_work_actually_look/",
        ],
        "required_fields": [
            "employees.employee_id", "employees.department", "employees.status",
            "position_history.employee_id", "position_history.position_name", "position_history.department",
            "performance_reviews.overall_score", "performance_reviews.review_date",
            "training_records.hours", "projects.project_value",
        ],
        "preflight_sql": """
WITH mobility AS (
 SELECT employee_id,
        CASE WHEN COUNT(DISTINCT position_name) > 1 OR COUNT(DISTINCT department) > 1 THEN 1 ELSE 0 END AS is_mobile
 FROM position_history GROUP BY employee_id
), latest_review AS (
 SELECT employee_id, overall_score,
        ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY review_date DESC, review_id DESC) rn
 FROM performance_reviews
), training AS (SELECT employee_id, SUM(hours) hours FROM training_records GROUP BY employee_id),
project_value AS (SELECT employee_id, SUM(project_value) value FROM projects GROUP BY employee_id)
SELECT COALESCE(m.is_mobile,0) is_mobile, COUNT(*) employee_count,
       AVG(CAST(lr.overall_score AS decimal(10,2))) avg_latest_score,
       AVG(CAST(COALESCE(t.hours,0) AS decimal(10,2))) avg_training_hours,
       AVG(CAST(COALESCE(p.value,0) AS decimal(18,2))) avg_project_value
FROM employees e
LEFT JOIN mobility m ON m.employee_id=e.employee_id
LEFT JOIN latest_review lr ON lr.employee_id=e.employee_id AND lr.rn=1
LEFT JOIN training t ON t.employee_id=e.employee_id
LEFT JOIN project_value p ON p.employee_id=e.employee_id
WHERE e.status=N'ปฏิบัติงาน'
GROUP BY COALESCE(m.is_mobile,0)
""".strip(),
    },
    "skills_project_risk": {
        "title": "Skills coverage vs project load and development investment",
        "question": (
            "สร้าง workforce risk matrix รายแผนกสำหรับพนักงานที่ยังปฏิบัติงาน โดยคำนวณ headcount, "
            "สัดส่วนพนักงานที่มี skill record, จำนวนทักษะเฉลี่ยต่อคน, years_of_experience เฉลี่ย, "
            "training hours เฉลี่ยต่อคน, performance review ล่าสุดเฉลี่ย และ project_value รวมต่อหัว "
            "ต้อง aggregate skills, training, reviews และ projects แยกเป็นหนึ่งแถวต่อพนักงานก่อน join "
            "จัดอันดับแผนกที่ project_value ต่อหัวสูงแต่ skill coverage หรือ training ต่ำว่าเสี่ยงที่สุด "
            "พร้อมอธิบายเกณฑ์ที่ใช้และข้อจำกัดของข้อมูล"
        ),
        "community_basis": (
            "People Analytics communities discuss performance gaps, learning behavior, skills, "
            "productivity and connecting people metrics to business outcomes."
        ),
        "sources": [
            "https://www.reddit.com/r/analytics/comments/13utqxk/hr_analytics/",
            "https://www.reddit.com/r/analytics/comments/1r40o7l/what_does_people_analytics_work_actually_look/",
            "https://www.shrm.org/in/executive-network/insights/how-chros-can-power-up-their-people-analytics--",
        ],
        "required_fields": [
            "employees.employee_id", "employees.department", "employees.status",
            "skills.employee_id", "skills.skill_name", "skills.years_of_experience",
            "training_records.hours", "performance_reviews.overall_score",
            "performance_reviews.review_date", "projects.project_value",
        ],
        "preflight_sql": """
WITH skill_agg AS (
 SELECT employee_id, COUNT(*) skill_count, AVG(CAST(years_of_experience AS decimal(10,2))) avg_skill_years
 FROM skills GROUP BY employee_id
), training AS (SELECT employee_id, SUM(hours) hours FROM training_records GROUP BY employee_id),
latest_review AS (
 SELECT employee_id, overall_score,
        ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY review_date DESC, review_id DESC) rn
 FROM performance_reviews
), project_value AS (SELECT employee_id, SUM(project_value) value FROM projects GROUP BY employee_id)
SELECT e.department, COUNT(*) headcount,
       SUM(CASE WHEN s.skill_count > 0 THEN 1 ELSE 0 END) employees_with_skills,
       AVG(CAST(COALESCE(s.skill_count,0) AS decimal(10,2))) avg_skill_count,
       AVG(CAST(COALESCE(t.hours,0) AS decimal(10,2))) avg_training_hours,
       AVG(CAST(lr.overall_score AS decimal(10,2))) avg_latest_score,
       SUM(COALESCE(p.value,0))/NULLIF(COUNT(*),0) project_value_per_head
FROM employees e
LEFT JOIN skill_agg s ON s.employee_id=e.employee_id
LEFT JOIN training t ON t.employee_id=e.employee_id
LEFT JOIN latest_review lr ON lr.employee_id=e.employee_id AND lr.rn=1
LEFT JOIN project_value p ON p.employee_id=e.employee_id
WHERE e.status=N'ปฏิบัติงาน'
GROUP BY e.department
ORDER BY project_value_per_head DESC
""".strip(),
    },
}
