# 05: 人物と参照音声を登録・選択する

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/5

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が名前付き人物の参照音声を登録し、別動画の対象話者として再利用できる。

**Blocked by:** 01: データ用フォルダを選んで既存データを開く; 02: ローカル動画を登録する

**Status:** ready-for-agent

## 完了条件

+- [ ] 音声ファイルとアプリ内動画の指定区間の双方から参照音声を登録でき、試聴・選択できる。
- [ ] 人物情報をフォルダ内のCSV、参照音声・特徴ファイルを別ファイルとして保存・再表示できる。
- [ ] 人物データの選択とモデル・閾値・分割方法を実装時に確認し、別動画で再利用できる。
