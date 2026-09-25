# 12: アプリからAviUtl2の画面と字幕を編集する

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/12

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が本アプリから画面と字幕を調整し、AviUtl2の結果をプレビューできる。

**Blocked by:** 10: 区間を選び、順番を決めて編集用動画を作る; 11: 編集可能な字幕をAviUtl2へ渡す

**Status:** implemented-locally

## 完了条件

- [x] 横・ショートの画面を編集開始時に選び、途中でも変更できる。
- [x] 字幕、拡大縮小、切り取り、配置をアプリから操作してプレビューできる。
- [x] 画面比率の変更時に既存配置を勝手に作り直さない。
- [x] アプリによる編集適用中は同じプロジェクトへの手編集を待つ。

## 検証

- Python テスト 35 件成功。
- AviUtl2 プラグインを MSVC でビルドし、実際のプロジェクトへ画面設定を適用して 180×320 のプレビューを生成。
- アプリのブリッジから字幕 v1 と v2 を順に別字幕として追加し、プレビュー更新を確認。
- AviUtl2 SDK の `call_edit_section` による排他的な編集セクションで適用。
