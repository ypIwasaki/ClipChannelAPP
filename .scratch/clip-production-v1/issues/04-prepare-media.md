# 04: 取得・登録動画を編集可能な媒体へ整える

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/4

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が取得・登録した通常のSDR動画を、正しい時刻で後続の解析と編集に使える。

**Blocked by:** 02: ローカル動画を登録する; 03: URLから動画・音声成果物を取得する

**Status:** ready-for-agent

## 完了条件

+- [ ] 形式と実ファイルの映像・音声開始位置を確認し、元動画時刻との対応を維持する。
- [ ] 必要な場合は元を保持したまま編集互換ファイルを別に作る。
- [ ] 変換失敗後も取得済みファイルを保持し、変換だけ再試行できる。
