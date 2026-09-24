# 01: データ用フォルダを選んで既存データを開く

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/1

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が直接接続されたドライブのデータ用フォルダを指定し、そこに保存された情報を再表示できる。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## 完了条件

+- [ ] 規定のフォルダ構成を作成し、既存のデータ用フォルダへ切り替えられる。
- [ ] 処理中または未保存入力がある間は切り替えを止め、理由を表示する。
- [ ] CSVの列、文字コード、時刻、引用符・改行、版の識別、保存中断時の扱いを決め、保存・再読込みで確認する。
- [ ] 依存物が不足しても保存済み情報は閲覧できる。
