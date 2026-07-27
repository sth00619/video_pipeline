# 레퍼런스 대본 코퍼스

`reference_scripts.jsonl`에는 권리·이용 범위가 확인된 대본만 넣습니다.
현재 외부 채널 원문은 제공되지 않았으므로 저장소에는 실제 레퍼런스 원문이나 임의로 만든 벤치마크 수치를 넣지 않았습니다.
`reference_baseline.json`은 이 상태를 명시하는 빈 템플릿이며, 실제 p10/p50/p90 수치가 아닙니다.

적재 후 아래 명령으로 실측 밴드를 만듭니다.

```powershell
python -m app.tools.build_reference_baseline --reference corpus/reference_scripts.jsonl --output corpus/reference_baseline.json
```

`benchmark_stock`은 반말/주식 타깃 밴드, `general_econ`은 비유·리듬 참고 밴드로만 사용합니다.
