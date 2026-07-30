import json
from pathlib import Path

from analyzer.competitor_analyzer import compare_reports


YOUR_REPORT = Path(
    "database/reports/https_www_python_org_20260730_200324.json"
)

COMPETITOR_REPORT = Path(
    "database/reports/https_fastapi_tiangolo_com_20260730_200512.json"
)


def load_report(path: Path) -> dict:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def main() -> None:
    your_report = load_report(YOUR_REPORT)
    competitor_report = load_report(
        COMPETITOR_REPORT
    )

    result = compare_reports(
        your_report=your_report,
        competitor_report=competitor_report,
    )

    print("\n" + "=" * 60)
    print("COMPETITOR COMPARISON")
    print("=" * 60)

    print(f"Website lu : {result['your_url']}")
    print(f"Competitor : {result['competitor_url']}")
    print(f"Winner     : {result['winner']}")

    print("\nPerbedaan:")

    for key, value in result["differences"].items():
        print(f"- {key}: {value}")

    print("\nRekomendasi:")

    for item in result["recommendations"]:
        print(f"- {item}")


if __name__ == "__main__":
    main()