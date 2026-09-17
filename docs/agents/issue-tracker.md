# Issue tracker: Local Markdown

- 機能ごとの保存先: `.scratch/<feature-slug>/`
- 仕様書: `spec.md`
- Issue: `issues/<NN>-<slug>.md`。01から採番し、1件1ファイルとする。
- 分類はファイル冒頭の `Status:` に記録する。
  値は `triage-labels.md` に従う。
- コメントは末尾の `## Comments` に追記する。
- 「公開」は該当するローカルファイルの作成・更新を意味する。
- Issue の取得時は指定パスを読む。
  番号だけで一意に特定できない場合は機能名を確認する。

## Wayfinder

- マップ: `.scratch/<effort>/map.md`
  Notes / Decisions-so-far / Fog を記録する。
- 子チケット: `.scratch/<effort>/issues/<NN>-<slug>.md`
- `Type:` は research / prototype / grilling / task。
- Wayfinder の `Status:` は open / claimed / resolved。
- `Blocked by: NN, NN` で依存先を記録する。
- 依存先がすべて resolved で、open のチケットから番号順に選ぶ。
- 作業前に claimed に更新する。
- 解決時は `## Answer` に回答を追記し、resolved に更新する。
  マップの Decisions-so-far に要旨とリンクを追記する。
