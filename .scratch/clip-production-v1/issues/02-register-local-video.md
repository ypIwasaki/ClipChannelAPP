# 02: ローカル動画を登録する

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/2

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が手元の動画を元ファイルを変えずに登録し、後続工程で選べる。

**Blocked by:** 01: データ用フォルダを選んで既存データを開く

**Status:** ready-for-agent

## 完了条件

+- [ ] 元ファイルをデータ用フォルダへコピーし、登録済み動画を再選択できる。
- [ ] 既存動画と同名の別動画は警告し、名前変更まで登録・解析を止める。既存動画の再解析は許す。
- [ ] 拡張子を除いた結果保存名の衝突を防ぎ、別動画の結果を既存版に混ぜない。
