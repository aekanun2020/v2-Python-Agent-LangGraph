# Finance MCP Ground Truth Q1–Q10

Generated from the read-only MSSQL MCP endpoint on 2026-07-30.

- Database: `TestDB`
- Fact table: `loans_fact`
- Period: 2016–2019
- Rows: 1,432,440
- Important semantic constraint: `loan_status` is a post-origination status.
  Neither `loan_status` nor `funded_amnt` is an approval/rejection decision.
- Currency metadata is absent; answers must not invent a currency.
- Rates are stored as fractions: `0.129953` means approximately `12.9953%`.

## Q1 — Portfolio size

**Question:** พอร์ตสินเชื่อทั้งหมดมีกี่รายการ ยอดวงเงินที่ขอและยอดที่ได้รับ funding
รวมเท่าใด และค่าเฉลี่ยต่อรายการเท่าใด?

**Logic/grain:** One output row over all rows in `loans_fact`.

```sql
SELECT COUNT_BIG(*) AS loan_count,
       SUM(loan_amnt) AS requested_total,
       SUM(funded_amnt) AS funded_total,
       AVG(loan_amnt) AS requested_avg,
       AVG(funded_amnt) AS funded_avg
FROM loans_fact;
```

**Ground truth:**

- `loan_count`: 1,432,440
- `requested_total`: 22,017,159,100
- `funded_total`: 22,017,131,100
- `requested_avg`: 15,370.388358
- `funded_avg`: 15,370.368811

## Q2 — Application mix

**Question:** สัดส่วนจำนวนรายการระหว่าง `Individual` และ `Joint App` เป็นเท่าใด?

**Logic/grain:** One row per canonical `application_type`; denominator is all loans.

```sql
SELECT a.application_type, COUNT_BIG(*) AS loan_count,
       CAST(100.0 * COUNT_BIG(*) / SUM(COUNT_BIG(*)) OVER ()
            AS decimal(10,4)) AS portfolio_pct
FROM loans_fact AS l
JOIN application_type_dim AS a
  ON l.application_type_id = a.application_type_id
GROUP BY a.application_type;
```

**Ground truth:**

| application_type | loan_count | portfolio_pct |
|---|---:|---:|
| Individual | 1,320,357 | 92.1754% |
| Joint App | 112,083 | 7.8246% |

## Q3 — Status distribution

**Question:** กระจายจำนวนและสัดส่วนสินเชื่อตาม `loan_status` อย่างไร?

**Logic/grain:** One row per exact canonical status; denominator is all loans.

```sql
SELECT s.loan_status, COUNT_BIG(*) AS loan_count,
       CAST(100.0 * COUNT_BIG(*) / SUM(COUNT_BIG(*)) OVER ()
            AS decimal(10,4)) AS portfolio_pct
FROM loans_fact AS l
JOIN loan_status_dim AS s ON l.loan_status_id = s.loan_status_id
GROUP BY s.loan_status;
```

**Ground truth:**

| loan_status | loan_count | portfolio_pct |
|---|---:|---:|
| Current | 702,223 | 49.0229% |
| Fully Paid | 551,955 | 38.5325% |
| Charged Off | 147,348 | 10.2865% |
| Late (31-120 days) | 18,752 | 1.3091% |
| In Grace Period | 7,928 | 0.5535% |
| Late (16-30 days) | 4,207 | 0.2937% |
| Default | 27 | 0.0019% |

## Q4 — Year cohorts

**Question:** แต่ละปีมีจำนวนรายการ วงเงิน funding เฉลี่ย และอัตราดอกเบี้ยเฉลี่ยเท่าใด?

**Logic/grain:** One row per `issue_d_dim.year`.

```sql
SELECT i.year, COUNT_BIG(*) AS loan_count,
       AVG(l.funded_amnt) AS avg_funded_amnt,
       AVG(l.int_rate) AS avg_int_rate
FROM loans_fact AS l
JOIN issue_d_dim AS i ON l.issue_d_id = i.issue_d_id
GROUP BY i.year;
```

**Ground truth:**

| year | loan_count | avg_funded_amnt | avg_int_rate |
|---:|---:|---:|---:|
| 2016 | 434,407 | 14,733.974591 | 13.0414% |
| 2017 | 387,116 | 14,858.279947 | 13.3674% |
| 2018 | 495,242 | 16,025.020394 | 12.7284% |
| 2019 | 115,675 | 16,671.263021 | 12.7200% |

## Q5 — Home-ownership segments

**Question:** แต่ละ `home_ownership` มีจำนวนรายการ วงเงิน funding เฉลี่ย
ดอกเบี้ยเฉลี่ย และ DTI เฉลี่ยเท่าใด?

**Logic/grain:** One row per exact `home_ownership` label. Do not suppress small groups.

```sql
SELECT h.home_ownership, COUNT_BIG(*) AS loan_count,
       AVG(l.funded_amnt) AS avg_funded_amnt,
       AVG(l.int_rate) AS avg_int_rate,
       AVG(l.dti) AS avg_dti
FROM loans_fact AS l
JOIN home_ownership_dim AS h
  ON l.home_ownership_id = h.home_ownership_id
GROUP BY h.home_ownership;
```

**Ground truth:**

| home_ownership | loan_count | avg_funded_amnt | avg_int_rate | avg_dti |
|---|---:|---:|---:|---:|
| MORTGAGE | 701,646 | 17,024.786039 | 12.5888% | 19.747853 |
| RENT | 556,961 | 13,544.125890 | 13.4838% | 18.540844 |
| OWN | 170,888 | 14,549.707557 | 13.0753% | 19.213482 |
| ANY | 2,940 | 14,206.037415 | 12.8239% | 18.384255 |
| NONE | 5 | 14,400.000000 | 13.1400% | 23.902000 |

## Q6 — Employment-length segments

**Question:** จำแนกตาม `emp_length` แล้ว กลุ่มใดมีวงเงิน funding เฉลี่ยสูงสุดและต่ำสุด?
รายงานจำนวน ดอกเบี้ยเฉลี่ย และ DTI เฉลี่ยประกอบด้วย

**Logic/grain:** One row per exact `emp_length`; extrema use `avg_funded_amnt`.

```sql
SELECT e.emp_length, COUNT_BIG(*) AS loan_count,
       AVG(l.funded_amnt) AS avg_funded_amnt,
       AVG(l.int_rate) AS avg_int_rate,
       AVG(l.dti) AS avg_dti
FROM loans_fact AS l
JOIN emp_length_dim AS e ON l.emp_length_id = e.emp_length_id
GROUP BY e.emp_length;
```

**Ground truth:**

- Highest: `10+ years` — 478,304 rows; funding average 16,514.623963;
  interest average 12.8512%; DTI average 19.227889.
- Lowest overall: `N/A` — 108,470 rows; funding average 12,263.196506;
  interest average 13.2071%; DTI average 22.875127.
- Lowest non-`N/A`: `1 year` — 95,926 rows; funding average 14,488.151023.

## Q7 — DTI buckets

**Question:** เมื่อแบ่ง DTI เป็น `<10`, `10-<20`, `20-<30`, `30+` และ `NULL`
แต่ละ bucket มีจำนวน วงเงิน funding เฉลี่ย และดอกเบี้ยเฉลี่ยเท่าใด?

**Logic/grain:** Boundaries are left-inclusive except `<10`; null is a separate bucket.

```sql
WITH bucketed AS (
  SELECT CASE
    WHEN dti IS NULL THEN 'NULL'
    WHEN dti < 10 THEN '<10'
    WHEN dti < 20 THEN '10-<20'
    WHEN dti < 30 THEN '20-<30'
    ELSE '30+' END AS dti_bucket,
    funded_amnt, int_rate
  FROM loans_fact
)
SELECT dti_bucket, COUNT_BIG(*) AS loan_count,
       AVG(funded_amnt) AS avg_funded_amnt,
       AVG(int_rate) AS avg_int_rate
FROM bucketed
GROUP BY dti_bucket;
```

**Ground truth:**

| dti_bucket | loan_count | avg_funded_amnt | avg_int_rate |
|---|---:|---:|---:|
| <10 | 254,841 | 14,533.541699 | 11.8884% |
| 10-<20 | 575,531 | 15,471.560611 | 12.4218% |
| 20-<30 | 432,491 | 15,527.219815 | 13.5834% |
| 30+ | 167,993 | 15,845.435524 | 15.1157% |
| NULL | 1,584 | 20,025.868056 | 14.0461% |

The observed ordered non-null buckets have increasing average interest rates. This is
descriptive association, not causality.

## Q8 — Fixed income bands

**Question:** สำหรับ `Individual` ที่มี `annual_inc` ให้แบ่งรายได้เป็น `<50000`,
`50000-<70000`, `70000-<100000` และ `100000+` แล้วเปรียบเทียบวงเงิน funding
ดอกเบี้ย และ DTI เฉลี่ย

**Logic/grain:** Apply fixed, left-inclusive bands after filtering Individual/non-null
income, then aggregate one row per band. Fixed boundaries avoid `NTILE` instability when
many rows tie at a quartile boundary and the fact table has no unique row identifier.

```sql
WITH ranked AS (
  SELECT CASE
           WHEN annual_inc < 50000 THEN '<50000'
           WHEN annual_inc < 70000 THEN '50000-<70000'
           WHEN annual_inc < 100000 THEN '70000-<100000'
           ELSE '100000+'
         END AS income_band,
         annual_inc, funded_amnt, int_rate, dti
  FROM loans_fact
  WHERE application_type = 'Individual' AND annual_inc IS NOT NULL
)
SELECT income_band, COUNT_BIG(*) AS loan_count,
       MIN(annual_inc) AS min_annual_inc, MAX(annual_inc) AS max_annual_inc,
       AVG(funded_amnt) AS avg_funded_amnt,
       AVG(int_rate) AS avg_int_rate, AVG(dti) AS avg_dti
FROM ranked
GROUP BY income_band;
```

**Ground truth:**

| income band | rows | income min–max | avg funded | avg interest | avg DTI |
|---:|---:|---:|---:|---:|---:|
| <50000 | 334,020 | 1,900–49,999.00 | 9,057.922205 | 13.7220% | 19.632060 |
| 50000-<70000 | 324,848 | 50,000–69,999.48 | 12,879.194808 | 13.1425% | 19.062727 |
| 70000-<100000 | 333,863 | 70,000–99,999.84 | 16,428.018079 | 12.8034% | 18.100492 |
| 100000+ | 327,626 | 100,000–61,000,000 | 21,591.207734 | 12.0991% | 15.801032 |

## Q9 — Funding gap by year

**Question:** แต่ละปีมีผลต่างระหว่างยอด `loan_amnt` กับ `funded_amnt` เท่าใด
และ funding ratio เป็นเท่าใด?

**Logic/grain:** One row per year. `funding_ratio = SUM(funded)/SUM(requested)`.

```sql
SELECT i.year,
       SUM(l.loan_amnt) AS requested_total,
       SUM(l.funded_amnt) AS funded_total,
       SUM(l.loan_amnt-l.funded_amnt) AS funding_gap,
       SUM(l.funded_amnt)/NULLIF(SUM(l.loan_amnt),0) AS funding_ratio
FROM loans_fact AS l
JOIN issue_d_dim AS i ON l.issue_d_id = i.issue_d_id
GROUP BY i.year;
```

**Ground truth:**

| year | requested_total | funded_total | gap | ratio |
|---:|---:|---:|---:|---:|
| 2016 | 6,400,569,700 | 6,400,541,700 | 28,000 | 0.999996 |
| 2017 | 5,751,877,900 | 5,751,877,900 | 0 | 1.000000 |
| 2018 | 7,936,263,150 | 7,936,263,150 | 0 | 1.000000 |
| 2019 | 1,928,448,350 | 1,928,448,350 | 0 | 1.000000 |

**Semantic trap:** This does not prove an approval rate. The table contains funded loans and
has no rejected-applications denominator or approval-decision field.

## Q10 — Dual-condition descriptive risk screen

**Question:** กลุ่ม `emp_length` ใดมีทั้งดอกเบี้ยเฉลี่ยและสัดส่วน `Charged Off`
สูงกว่าค่าเฉลี่ยทั้งพอร์ต?

**Logic/grain:** Compute portfolio benchmarks first, then one row per employment-length
segment. A segment passes only when both comparisons are strictly `>`.

```sql
WITH overall AS (
  SELECT AVG(l.int_rate) AS overall_avg_int_rate,
         AVG(CASE WHEN s.loan_status='Charged Off' THEN 1.0 ELSE 0.0 END)
           AS overall_charged_off_rate
  FROM loans_fact AS l
  JOIN loan_status_dim AS s ON l.loan_status_id=s.loan_status_id
),
segments AS (
  SELECT e.emp_length, COUNT_BIG(*) AS loan_count,
         AVG(l.int_rate) AS avg_int_rate,
         AVG(CASE WHEN s.loan_status='Charged Off' THEN 1.0 ELSE 0.0 END)
           AS charged_off_rate
  FROM loans_fact AS l
  JOIN emp_length_dim AS e ON l.emp_length_id=e.emp_length_id
  JOIN loan_status_dim AS s ON l.loan_status_id=s.loan_status_id
  GROUP BY e.emp_length
)
SELECT s.*, o.*
FROM segments AS s CROSS JOIN overall AS o;
```

**Portfolio benchmarks:**

- Average interest: 12.9953%
- Charged-off share: 10.2865%

**Segments meeting both strict conditions:**

| emp_length | rows | avg interest | charged-off share |
|---|---:|---:|---:|
| N/A | 108,470 | 13.2071% | 13.2119% |
| 1 year | 95,926 | 13.1982% | 10.8875% |
| 2 years | 130,251 | 13.0903% | 10.5603% |
| 3 years | 116,802 | 13.1003% | 10.5520% |
| 5 years | 88,686 | 13.0683% | 10.3139% |

This is a descriptive screen, not a causal model or an individual lending decision.

## Deterministic evaluation rules

1. Every requested numeric claim must match ground truth within the declared rounding.
2. Canonical labels must match evidence exactly.
3. Percentages may be expressed as fractions or percentages only when conversion is correct.
4. Do not invent currency units.
5. Do not call `Current`, `Fully Paid`, or `funded_amnt` an approval decision.
6. Do not make causal claims from grouped descriptive statistics.
7. Q7 boundaries, Q8 fixed bands/filtered population, Q9 denominator, and Q10 strict dual conditions
   are part of the answer contract.
8. If evidence cannot support a requested decision, the correct result is an explicit
   insufficiency/refusal plus the supported descriptive facts.
