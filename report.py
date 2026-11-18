"""Render the observed benchmark as a portable comparison."""
from html import escape


def write_report(path, summary):
    body = []
    for area, choices in summary["test"].items():
        baseline = choices["weekly_naive"]["mae_mw"]
        for name, metric in choices.items():
            mae = metric["mae_mw"]
            coverage = metric.get("coverage_80pct")
            interval = f"{coverage:.1%}" if coverage is not None else "—"
            body.append(
                f'<tr><th scope="row">{escape(area)} · {escape(name.replace("_", " "))}</th>'
                f'<td>{metric["rows"]:,}</td><td>{mae:,.1f}</td>'
                f'<td>{mae / baseline:.2f}×</td><td>{interval}</td></tr>'
            )
    html = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grid load transfer benchmark</title>
<style>
body{{font:16px/1.55 system-ui;max-width:60rem;margin:2rem auto;padding:0 1rem;color:#122a32;background:#f6faf9}}
table{{border-collapse:collapse;width:100%;background:white}} th,td{{border-bottom:1px solid #dae6e7;padding:.65rem;text-align:left}}
thead{{background:#dfeeea}} h1{{letter-spacing:-.04em}} a{{color:#075766}} .scroll{{overflow:auto}}
</style>
<h1>Day-ahead grid load · 2020 holdout</h1>
<p>Compare Germany and Austria against the weekly naive forecast. Each forecast is issued at local noon one day before target delivery.</p>
<div class="scroll"><table><thead><tr><th>Target and model</th><th>Hours</th><th>MAE (MW)</th>
<th>MAE / weekly naive MAE</th><th>80% interval coverage</th></tr></thead>
<tbody>{''.join(body)}</tbody></table></div>
<p><a href="metrics.json">Metrics and diagnostics</a> · <a href="predictions.csv">Hourly predictions</a></p>
</html>
"""
    path.write_text(html, encoding="utf-8")
