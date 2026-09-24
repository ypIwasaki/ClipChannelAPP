# 12: アプリからAviUtl2の画面と字幕を編集する

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/12

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が本アプリから画面と字幕を調整し、AviUtl2の結果をプレビューできる。

**Blocked by:** 10: 区間を選び、順番を決めて編集用動画を作る; 11: 編集可能な字幕をAviUtl2へ渡す

**Status:** ready-for-agent

## 完了条件

+- [ ] 横・ショートの画面を編集開始時に選び、途中でも変更できる。
- [ ] 字幕、拡大縮小、切り取り、配置をアプリから操作してプレビューできる。
- [ ] 画面比率の変更時に既存配置を勝手に作り直さない。
- [ ] アプリによる編集適用中は同じプロジェクトへの手編集を待つ。
