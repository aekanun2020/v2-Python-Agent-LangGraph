"""Deterministic grader for the unseen Finance Q1-Q10 suite."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQUIRED = {
    "Q01": (
        "loan_count=1432440",
        "requested_total=22017159100.00",
        "funded_total=22017131100.00",
        "requested_avg=15370.388358",
        "funded_avg=15370.368811",
        "ไม่มี currency metadata",
    ),
    "Q02": (
        "application_type=individual; loan_count=1320357; portfolio_pct=92.1754",
        "application_type=joint app; loan_count=112083; portfolio_pct=7.8246",
    ),
    "Q03": (
        "loan_status=current; loan_count=702223; portfolio_pct=49.0229",
        "loan_status=fully paid; loan_count=551955; portfolio_pct=38.5325",
        "loan_status=charged off; loan_count=147348; portfolio_pct=10.2865",
        "loan_status=late (31-120 days); loan_count=18752; portfolio_pct=1.3091",
        "loan_status=in grace period; loan_count=7928; portfolio_pct=0.5535",
        "loan_status=late (16-30 days); loan_count=4207; portfolio_pct=0.2937",
        "loan_status=default; loan_count=27; portfolio_pct=0.0019",
        "ไม่ใช่ผลอนุมัติหรือปฏิเสธ",
    ),
    "Q04": tuple(
        f"year={year}; loan_count={count}; avg_funded_amnt={funded}; avg_int_rate_pct={rate}"
        for year, count, funded, rate in (
            ("2016", "434407", "14733.974591", "13.041364"),
            ("2017", "387116", "14858.279947", "13.367410"),
            ("2018", "495242", "16025.020394", "12.728426"),
            ("2019", "115675", "16671.263021", "12.719964"),
        )
    ),
    "Q05": tuple(
        f"home_ownership={label}; loan_count={count}; avg_funded_amnt={funded}; avg_int_rate_pct={rate}; avg_dti={dti}"
        for label, count, funded, rate, dti in (
            ("mortgage", "701646", "17024.786039", "12.588802", "19.747853"),
            ("rent", "556961", "13544.125890", "13.483818", "18.540844"),
            ("own", "170888", "14549.707557", "13.075346", "19.213482"),
            ("any", "2940", "14206.037415", "12.823949", "18.384255"),
            ("none", "5", "14400.000000", "13.140000", "23.902000"),
        )
    ),
    "Q06": (
        "extreme_type=highest; emp_length=10+ years; loan_count=478304; avg_funded_amnt=16514.623963; avg_int_rate_pct=12.851166; avg_dti=19.227889",
        "extreme_type=lowest_overall; emp_length=n/a; loan_count=108470; avg_funded_amnt=12263.196506; avg_int_rate_pct=13.207055; avg_dti=22.875127",
        "extreme_type=lowest_non_na; emp_length=1 year; loan_count=95926; avg_funded_amnt=14488.151023; avg_int_rate_pct=13.198205; avg_dti=18.420589",
    ),
    "Q07": tuple(
        f"dti_bucket={label}; loan_count={count}; avg_funded_amnt={funded}; avg_int_rate_pct={rate}"
        for label, count, funded, rate in (
            ("<10", "254841", "14533.541699", "11.888448"),
            ("10-<20", "575531", "15471.560611", "12.421760"),
            ("20-<30", "432491", "15527.219815", "13.583355"),
            ("30+", "167993", "15845.435524", "15.115695"),
            ("null", "1584", "20025.868056", "14.046143"),
        )
    ),
    "Q08": tuple(
        f"income_band={label}; loan_count={count}; min_annual_inc={minimum}; max_annual_inc={maximum}; avg_funded_amnt={funded}; avg_int_rate_pct={rate}; avg_dti={dti}"
        for label, count, minimum, maximum, funded, rate, dti in (
            ("<50000", "334020", "1900.0", "49999.00", "9057.922205", "13.721959", "19.632060"),
            ("50000-<70000", "324848", "50000.0", "69999.48", "12879.194808", "13.142466", "19.062727"),
            ("70000-<100000", "333863", "70000.0", "99999.84", "16428.018079", "12.803399", "18.100492"),
            ("100000+", "327626", "100000.0", "61000000.00", "21591.207734", "12.099061", "15.801032"),
        )
    ),
    "Q09": tuple(
        f"year={year}; requested_total={requested}; funded_total={funded}; funding_gap={gap}; funding_ratio={ratio}"
        for year, requested, funded, gap, ratio in (
            ("2016", "6400569700.00", "6400541700.00", "28000.00", "0.99999563"),
            ("2017", "5751877900.00", "5751877900.00", "0.00", "1.00000000"),
            ("2018", "7936263150.00", "7936263150.00", "0.00", "1.00000000"),
            ("2019", "1928448350.00", "1928448350.00", "0.00", "1.00000000"),
        )
    ) + ("funding_ratio ไม่ใช่ approval rate",),
    "Q10": tuple(
        f"emp_length={label}; loan_count={count}; avg_int_rate_pct={rate}; charged_off_rate_pct={charged}"
        for label, count, rate, charged in (
            ("n/a", "108470", "13.207055", "13.2119"),
            ("1 year", "95926", "13.198205", "10.8875"),
            ("2 years", "130251", "13.090283", "10.5603"),
            ("3 years", "116802", "13.100319", "10.5520"),
            ("5 years", "88686", "13.068333", "10.3139"),
        )
    ) + ("ไม่ใช่ causal model หรือคำตัดสินสินเชื่อรายบุคคล",),
}

FORBIDDEN = (
    "ควรเพิ่ม",
    "ควรลด",
    "โอกาสในการพัฒนา",
    "มีประสิทธิภาพ",
    "สถานการณ์เศรษฐกิจ",
    "ตอบสนองความต้องการ",
    "บาท",
    "ดอลลาร์",
    " usd",
    " thb",
)


def grade(payload: dict) -> dict:
    results = []
    for record in payload["records"]:
        qid = record["id"]
        answer = record["answer"].lower().replace(",", "")
        checks = [
            {
                "claim": expected,
                "passed": expected.lower().replace(",", "") in answer,
            }
            for expected in REQUIRED[qid]
        ]
        checks.extend({
            "claim": f"forbidden:{term}",
            "passed": term not in answer,
        } for term in FORBIDDEN)
        results.append({
            "id": qid,
            "passed": (
                record["exit_code"] == 0
                and not record["timeout"]
                and all(item["passed"] for item in checks)
            ),
            "checks": checks,
        })
    encoded = json.dumps(results, ensure_ascii=False, sort_keys=True)
    return {
        "grader": "finance-skill-atomic-v1",
        "questions_passed": sum(item["passed"] for item in results),
        "questions_total": len(results),
        "atomic_passed": sum(
            check["passed"] for item in results for check in item["checks"]
        ),
        "atomic_total": sum(len(item["checks"]) for item in results),
        "result_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = grade(json.loads(args.artifact.read_text(encoding="utf-8")))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(
        f"questions={result['questions_passed']}/{result['questions_total']} "
        f"atomic={result['atomic_passed']}/{result['atomic_total']} "
        f"sha256={result['result_sha256']}"
    )


if __name__ == "__main__":
    main()
